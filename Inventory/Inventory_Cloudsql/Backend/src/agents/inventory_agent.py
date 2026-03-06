from __future__ import annotations
from typing import Dict, Any
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import CLOUDSQL_TABLESCHEMA


@status_broadcast("Inventory Agent is Working")
async def inventory_snapshot(
    broadcast, engine, store_id: int, sku: str
) -> Dict[str, Any]:
    """
    Retrieves an inventory snapshot for a given store–SKU from `{CLOUDSQL_TABLESCHEMA}.stock_levels`
    and returns normalized planning fields.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        engine: SQLAlchemy engine used to execute the query.
        store_id (int): Store identifier to filter stock levels.
        sku (str): Product SKU whose inventory metrics are requested.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - on_hand (float): Units physically available in-store.
            - in_transit (float): Units expected to arrive (already ordered).
            - safety_stock (float): Buffer stock for variability and delays.
            - reorder_point (float): Threshold that triggers replenishment.
        When no record exists, returns safe defaults with zeros.
    """

    # -------------------------------------------------------------------------
    # Query inventory planning fields for the target store–SKU.
    # -------------------------------------------------------------------------
    query = text(
        f"""
        SELECT on_hand, in_transit, safety_stock, reorder_point
        FROM {CLOUDSQL_TABLESCHEMA}.stock_levels
        WHERE store_id = :store_id AND sku = :sku
    """
    )

    # Execute the query and fetch dict-like rows via mappings().
    with engine.connect() as connection:
        result = connection.execute(query, {"store_id": store_id, "sku": sku})
    rows = result.mappings().all()

    # Normalize and coerce values to float; default to 0 for missing/nulls.
    cleaned_rows = []
    if rows:
        for row in rows:
            cleaned_rows.append(
                {
                    "on_hand": float(row.get("on_hand") or 0),
                    "in_transit": float(row.get("in_transit") or 0),
                    "safety_stock": float(row.get("safety_stock") or 0),
                    "reorder_point": float(row.get("reorder_point") or 0),
                }
            )
    else:
        # Safe default when the store–SKU has no stock_levels record.
        cleaned_rows.append(
            {"on_hand": 0, "in_transit": 0, "safety_stock": 0, "reorder_point": 0}
        )

    return cleaned_rows[0]
