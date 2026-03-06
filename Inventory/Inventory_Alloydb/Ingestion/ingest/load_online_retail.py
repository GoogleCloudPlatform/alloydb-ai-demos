from __future__ import annotations
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.utils.sql import get_conn, execute

load_dotenv()
MAX_ROWS = int(os.getenv("MAX_ROWS", "5000"))
CSV_PATH = os.getenv("KAGGLE_LOCAL_CSV", "./data/online_retail_II.csv")


def _read_input(path: Path) -> pd.DataFrame:
    """
    Read CSV or Excel robustly.
    - Try default CSV parsing first
    - Fall back to sep=None sniffing
    - Support .xlsx via openpyxl
    """
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at: {path.resolve()}")
    suffix = path.suffix.lower()

    if suffix in [".xlsx", ".xls"]:
        # Excel path
        engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
        return pd.read_excel(path, engine=engine, nrows=MAX_ROWS)

    # CSV path
    try:
        return pd.read_csv(path, nrows=MAX_ROWS)
    except Exception:
        # sniff delimiter
        return pd.read_csv(path, nrows=MAX_ROWS, sep=None, engine="python")


def _pick_column(cols: dict[str, str], *candidates: str) -> str | None:
    """Pick the first existing column from candidate names (case-insensitive)."""
    for c in candidates:
        c_norm = c.strip().lower()
        if c_norm in cols:
            return cols[c_norm]
    return None


def upsert_store():
    execute("""
        INSERT INTO retail.stores(code, name, region, timezone)
        VALUES ('WEB','Web Store','UK','Europe/London')
        ON CONFLICT DO NOTHING;
    """)


def load_data():
    path = Path(CSV_PATH)
    df = _read_input(path)

    # Build a case-insensitive map to original column names
    cols_map = {c.strip().lower(): c for c in df.columns}

    # Resolve schema differences across Online Retail v1/v2 variants
    sku_col      = _pick_column(cols_map, "stockcode")
    title_col    = _pick_column(cols_map, "description")
    date_col     = _pick_column(cols_map, "invoicedate", "invoice date")
    qty_col      = _pick_column(cols_map, "quantity", "qty")
    price_col    = _pick_column(cols_map, "unitprice", "price")
    country_col  = _pick_column(cols_map, "country")
    invoice_col  = _pick_column(cols_map, "invoiceno", "invoice")

    required = {
        "sku": sku_col, "title": title_col, "order_ts": date_col,
        "quantity": qty_col, "unit_price": price_col, "country": country_col,
        "order_id": invoice_col
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        pretty_cols = ", ".join(df.columns)
        raise SystemExit(
            "❌ Ingestion failed: missing columns for keys "
            f"{missing}. Found columns: {pretty_cols}\n"
            "Tip: ensure you downloaded Online Retail / Online Retail II and that the header row is present."
        )

    # Select and normalize
    use = df[[invoice_col, sku_col, title_col, date_col, qty_col, price_col, country_col]].copy()
    use = use.rename(columns={
        invoice_col: "order_id",
        sku_col: "sku",
        title_col: "title",
        date_col: "order_ts",
        qty_col: "Quantity",
        price_col: "unit_price",
        country_col: "country",
    })

    # Coerce, clean
    use["order_ts"] = pd.to_datetime(use["order_ts"], errors="coerce")
    use = use.dropna(subset=["sku", "title", "order_ts", "Quantity", "unit_price"])
    # Positive quantities / non-negative price
    use = use[use["Quantity"] > 0]
    use = use[use["unit_price"] >= 0]

    # Upsert products & write transactions
    products = use[["sku", "title"]].drop_duplicates()

    with get_conn() as conn, conn.cursor() as cur:
        # Get WEB store_id
        cur.execute("SELECT store_id FROM retail.stores WHERE code='WEB'")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("Store 'WEB' not found; run upsert_store() first.")
        store_id = row["store_id"]

        # Upsert products
        cur.executemany(
            "INSERT INTO retail.products (sku, title) VALUES (%s, %s) "
            "ON CONFLICT (sku) DO UPDATE SET title = EXCLUDED.title",
            list(products.itertuples(index=False, name=None))
        )

        # Prepare transactions
        tx_rows = []
        for r in use.itertuples(index=False):
            tx_rows.append((
                r.order_id, r.order_ts, store_id, "online",
                r.sku, int(r.Quantity), float(r.unit_price), r.country
            ))

        cur.executemany("""
            INSERT INTO retail.transactions
              (order_id, order_ts, store_id, channel, sku, quantity, unit_price, country)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, tx_rows)

        conn.commit()

    print(f"✅ Loaded {len(products)} products and {len(use)} transactions from {path}")


if __name__ == "__main__":
    try:
        upsert_store()
        load_data()
    except Exception as e:
        print("❌ Error:", e, file=sys.stderr)
        raise
