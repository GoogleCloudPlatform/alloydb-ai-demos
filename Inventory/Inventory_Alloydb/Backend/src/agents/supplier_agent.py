from __future__ import annotations
from typing import List, Dict, Any
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import ALLOYDB_TABLESCHEMA


@status_broadcast("Supplier Agent is Working")
async def supplier_options(broadcast, engine, sku: str) -> List[Dict[str, Any]]:
    """
    Retrieves supplier proposals for a given SKU and normalizes them for
    downstream decisioning (MOQ, lead time, cost, preference).

    The query joins product-specific supplier overrides with supplier defaults,
    and applies COALESCE to use product-level overrides when available.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        engine: SQLAlchemy engine used to execute the database query.
        sku (str): Product SKU for which supplier options are requested.

    Returns:
        List[Dict[str, Any]]: A list of proposal dictionaries, each containing:
            - supplier_id (int): Unique supplier identifier.
            - name (str): Supplier display name.
            - lead_time_days (int): Expected lead time (days) for delivery.
            - moq (int): Minimum order quantity enforced by the supplier.
            - cost (float): Unit cost quoted by the supplier.
            - preferred (bool): Whether the supplier is marked as preferred.
        The list is ordered by preference (descending) then by cost (ascending).
    """

    # -------------------------------------------------------------------------
    # Query supplier proposals for the target SKU.
    # - COALESCE(ps.lead_time_days, s.lead_time_days): product-level override
    #   falls back to supplier default when missing.
    # - COALESCE(ps.moq, s.moq): product-level MOQ override or supplier default.
    # - ORDER BY preferred DESC, cost ASC: prioritize preferred, then lower cost.
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
        FROM {ALLOYDB_TABLESCHEMA}.product_suppliers ps
        JOIN {ALLOYDB_TABLESCHEMA}.suppliers s ON s.supplier_id = ps.supplier_id
        WHERE ps.sku = :sku
        ORDER BY ps.preferred DESC, ps.cost ASC
    """
    )

    # Execute the query; use mappings() for dict-like row access by column name.
    with engine.connect() as connection:
        # rows = connection.execute(query, {"sku": sku}).fetchall()
        result = connection.execute(query, {"sku": sku})

    # Convert to a list of mapping rows to safely access fields by name.
    rows = result.mappings().all()

    # Normalize each row into a strongly-typed dictionary with safe defaults.
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

    # -------------------------------------------------------------------------
    # Return the normalized proposals; also print for quick visibility/debugging.
    # -------------------------------------------------------------------------
    print("Supplier:", cleaned_rows)
    return cleaned_rows
