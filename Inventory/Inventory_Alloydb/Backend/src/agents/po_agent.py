from __future__ import annotations
from typing import List, Dict, Any
from datetime import date, timedelta
from sqlalchemy import text
from src.utils.broadcast_decorator import status_broadcast
from src.utils.config import ALLOYDB_TABLESCHEMA


@status_broadcast("PO Agent is working")
async def create_po(
    broadcast,
    engine,
    supplier_id: int,
    lines: List[Dict[str, Any]],
    created_by: str = "agent",
) -> int:
    """
    Creates a purchase order (PO) and its line items for a given supplier, then
    updates the PO total and commits the transaction.

    The function performs the following steps:
      1) Insert a draft PO with an expected arrival date.
      2) Insert each provided line item (SKU, qty, cost, promised date).
      3) Accumulate line values to compute the PO total.
      4) Update the PO with the computed total and commit.

    Args:
        broadcast: Orchestration or messaging object used by the status decorator.
        engine: SQLAlchemy engine used to execute database operations.
        supplier_id (int): Identifier of the supplier associated with the PO.
        lines (List[Dict[str, Any]]): Line items with keys:
            - sku (str): Product SKU to order.
            - qty (int | str): Quantity to order (coerced to int).
            - unit_cost (float | str): Unit price (coerced to float).
            - lead_time_days (int, optional): Days until the supplier promises delivery.
        created_by (str, optional): Creator label for audit; defaults to "agent".

    Returns:
        int: The newly created purchase order identifier (`po_id`).

    Raises:
        Exception: Propagates any exception encountered during PO creation,
        after logging a failure message.
    """
    # Open a DB connection for the transactional sequence that follows.
    with engine.connect() as conn:
        try:
            # -----------------------------------------------------------------
            # Step 1: Create a draft PO and capture its identifier.
            # - expected_at: today + 7 days (default receiving expectation).
            # -----------------------------------------------------------------
            result = conn.execute(
                text(
                    f"""
                INSERT INTO {ALLOYDB_TABLESCHEMA}.purchase_orders (supplier_id, status, created_by, expected_at)
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

            # Initialize running total for the PO (sum of qty * unit_cost).
            total = 0.0

            # -----------------------------------------------------------------
            # Step 2: Insert each PO line item and accumulate the PO total.
            # - promised_at: today + lead_time_days (defaults to 7 if missing).
            # - qty/unit_cost are coerced to int/float for arithmetic safety.
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
                    INSERT INTO {ALLOYDB_TABLESCHEMA}.purchase_order_lines (po_id, sku, qty, unit_cost, promised_at)
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
            # Step 3: Update the PO header with the computed total amount.
            # -----------------------------------------------------------------
            conn.execute(
                text(
                    f"UPDATE {ALLOYDB_TABLESCHEMA}.purchase_orders SET total_amount = :total WHERE po_id = :po_id"
                ),
                {"total": total, "po_id": po_id},
            )

            # -----------------------------------------------------------------
            # Step 4: Commit the transaction to persist header + lines + total.
            # -----------------------------------------------------------------
            conn.commit()
            print(f"✅ PO created successfully: PO ID {po_id}")
            return po_id

        except Exception as e:
            # Surface failure context; re-raise to let caller handle errors upstream.
            print(f"❌ PO creation failed: {e}")
            raise
