from __future__ import annotations
from typing import Dict, Any
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import ALLOYDB_TABLESCHEMA


@status_broadcast("Inventory Agent is Working")
async def inventory_snapshot(
    broadcast, engine, store_id: int, sku: str
) -> Dict[str, Any]:
    """
    Retrieves a snapshot of inventory planning values for a given store–SKU.

    The function reads the current operational inventory metrics from
    `{ALLOYDB_TABLESCHEMA}.stock_levels` and returns a normalized dictionary suitable for
    downstream planning logic.

    Args:
        broadcast: Orchestration or messaging object used by the status decorator.
        engine: SQLAlchemy engine used to execute the database query.
        store_id (int): Store identifier whose inventory snapshot is requested.
        sku (str): Product SKU for which inventory values are fetched.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - on_hand (float): Current physical stock available.
            - in_transit (float): Quantity expected to arrive (already ordered/shipped).
            - safety_stock (float): Buffer stock to protect against demand variability.
            - reorder_point (float): Threshold that triggers replenishment.
        If no rows are found, returns all fields as 0 to provide a safe default.
    """

    # -------------------------------------------------------------------------
    # Query inventory planning fields for the target store–SKU.
    #   - on_hand: units physically in stock
    #   - in_transit: units expected from existing POs/shipments
    #   - safety_stock: buffer to mitigate variability and delays
    #   - reorder_point: level at which replenishment should be triggered
    # -------------------------------------------------------------------------
    query = text(
        f"""
        SELECT on_hand, in_transit, safety_stock, reorder_point
        FROM {ALLOYDB_TABLESCHEMA}.stock_levels
        WHERE store_id = :store_id AND sku = :sku
    """
    )

    # Execute the query using the provided SQLAlchemy engine.
    # Using `mappings()` later allows name-based access (dict-like rows).
    with engine.connect() as connection:
        result = connection.execute(query, {"store_id": store_id, "sku": sku})

    # Convert rows to a list of mapping objects for consistent key access.
    rows = result.mappings().all()

    # Prepare a clean, normalized list of dicts with float-casting and defaults.
    cleaned_rows = []
    if rows:
        # Iterate each row and coerce None/missing values to 0; cast to float.
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
        # Safe default when the store–SKU is absent in `stock_levels`.
        cleaned_rows.append(
            {"on_hand": 0, "in_transit": 0, "safety_stock": 0, "reorder_point": 0}
        )

    # Return the first (and typically only) snapshot dictionary.
    return cleaned_rows[0]
