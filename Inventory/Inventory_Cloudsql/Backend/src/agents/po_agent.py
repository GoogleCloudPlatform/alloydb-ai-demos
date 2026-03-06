from __future__ import annotations
from typing import List, Dict, Any
from datetime import date, timedelta
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import CLOUDSQL_TABLESCHEMA


@status_broadcast("PO Agent is working")
async def create_po(
    broadcast,
    engine,
    supplier_id: int,
    lines: List[Dict[str, Any]],
    created_by: str = "agent",
) -> int:
    """
    Creates a draft Purchase Order (PO) header, inserts line items, updates the
    PO total amount, commits the transaction, and returns the new PO id.

    Steps performed:
        1) Insert PO header with supplier_id, status='draft', created_by, expected_at.
        2) Insert each line item (sku, qty, unit_cost, promised_at).
        3) Accumulate total from qty * unit_cost across lines.
        4) Update PO header with computed total_amount.
        5) Commit and return `po_id`.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        engine: SQLAlchemy engine used for database operations.
        supplier_id (int): Supplier identifier for the PO.
        lines (List[Dict[str, Any]]): Line items containing:
            - sku (str), qty (int/str), unit_cost (float/str), lead_time_days (int, optional).
        created_by (str, optional): Creator identifier for audit trail; defaults to 'agent'.

    Returns:
        int: Newly created purchase order id (`po_id`).

    Raises:
        Exception: Re-raises any exception encountered during DB operations after logging.
    """
    # Open a connection for the transactional sequence.
    with engine.connect() as conn:
        try:
            # -----------------------------------------------------------------
            # Insert PO header and retrieve the generated `po_id`.
            # `expected_at` default set to 7 days from today.
            # -----------------------------------------------------------------
            result = conn.execute(
                text(
                    f"""
                INSERT INTO {CLOUDSQL_TABLESCHEMA}.purchase_orders (supplier_id, status, created_by, expected_at)
                VALUES (:supplier_id, 'draft', :created_by, :expected_at)
                RETURNING po_id
                """
                ),
                {
                    "supplier_id": supplier_id,
                    "created_by": created_by,
                    "expected_at": date.today() + timedelta(days=7),
                },
            )
            po_id = result.scalar_one()

            # Running total of the PO value (sum of qty * unit_cost).
            total = 0.0

            # -----------------------------------------------------------------
            # Insert each PO line item and accumulate the total.
            # `promised_at` uses provided lead_time_days or defaults to 7 days.
            # -----------------------------------------------------------------
            for ln in lines:
                qty = int(ln["qty"])
                cost = float(ln["unit_cost"])
                promised = date.today() + timedelta(
                    days=int(ln.get("lead_time_days", 7))
                )
                total += qty * cost

                conn.execute(
                    text(
                        f"""
                    INSERT INTO {CLOUDSQL_TABLESCHEMA}.purchase_order_lines (po_id, sku, qty, unit_cost, promised_at)
                    VALUES (:po_id, :sku, :qty, :unit_cost, :promised_at)
                    """
                    ),
                    {
                        "po_id": po_id,
                        "sku": ln["sku"],
                        "qty": qty,
                        "unit_cost": cost,
                        "promised_at": promised,
                    },
                )

            # -----------------------------------------------------------------
            # Update PO header with the computed `total_amount`.
            # -----------------------------------------------------------------
            conn.execute(
                text(
                    f"UPDATE {CLOUDSQL_TABLESCHEMA}.purchase_orders SET total_amount = :total WHERE po_id = :po_id"
                ),
                {"total": total, "po_id": po_id},
            )
            conn.commit()
            print(f"✅ PO created successfully: PO ID {po_id}")
            return po_id

        except Exception as e:
            print(f"❌ PO creation failed: {e}")
            raise
