from __future__ import annotations
from typing import List, Dict, Any
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import CLOUDSQL_TABLESCHEMA


@status_broadcast("Supplier Agent is Working")
async def supplier_options(broadcast, engine, sku: str) -> List[Dict[str, Any]]:
    """
    Retrieves normalized supplier proposals for a given SKU, including
    lead time, MOQ, unit cost, and preference flag.

    The query joins product-specific overrides (`{CLOUDSQL_TABLESCHEMA}.product_suppliers`) with
    supplier defaults (`{CLOUDSQL_TABLESCHEMA}.suppliers`), using `COALESCE` so that product-level
    overrides take precedence when present.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        engine: SQLAlchemy engine used to execute the database query.
        sku (str): Product SKU for which supplier proposals are requested.

    Returns:
        List[Dict[str, Any]]: Ordered list (preferred DESC, cost ASC) where each item contains:
            - supplier_id (int): Unique supplier identifier.
            - name (str): Supplier name.
            - lead_time_days (int): Expected delivery lead time in days.
            - moq (int): Minimum order quantity.
            - cost (float): Unit cost quoted by the supplier.
            - preferred (bool): Whether the supplier is marked as preferred.
    """

    # -------------------------------------------------------------------------
    # Query supplier proposals for the SKU:
    # - COALESCE(product-level override, supplier default) for lead_time_days and moq.
    # - ORDER BY preferred DESC then cost ASC to prioritize preferred and cheaper options.
    # -------------------------------------------------------------------------
    query = text(
        f"""
        SELECT 
            ps.supplier_id,
            s.name,
            COALESCE(ps.lead_time_days, s.lead_time_days) AS lead_time_days,
            COALESCE(ps.moq, s.moq) AS moq,
            ps.cost,
            ps.preferred
        FROM {CLOUDSQL_TABLESCHEMA}.product_suppliers ps
        JOIN {CLOUDSQL_TABLESCHEMA}.suppliers s ON s.supplier_id = ps.supplier_id
        WHERE ps.sku = :sku
        ORDER BY ps.preferred DESC, ps.cost ASC
    """
    )

    # Execute and fetch dict-like rows using mappings() for safer field access by name.
    with engine.connect() as connection:
        # rows = connection.execute(query, {"sku": sku}).fetchall()
        result = connection.execute(query, {"sku": sku})
    rows = result.mappings().all()

    # Normalize types and provide safe defaults for missing values.
    cleaned_rows = []
    for row in rows:
        cleaned_rows.append(
            {
                "supplier_id": int(row.get("supplier_id") or 0),
                "name": row.get("name"),
                "lead_time_days": int(row.get("lead_time_days") or 0),
                "moq": int(row.get("moq") or 0),
                "cost": float(row.get("cost") or 0.0),
                "preferred": bool(row.get("preferred")),
            }
        )
    return cleaned_rows
