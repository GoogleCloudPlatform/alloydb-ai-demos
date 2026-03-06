from __future__ import annotations
from dataclasses import dataclass
from math import ceil
from typing import Dict, List, Tuple, Any
from sqlalchemy import text
from src.agents.demand_agent import forecast_sku_store
from src.agents.inventory_agent import inventory_snapshot
from src.agents.supplier_agent import supplier_options
from src.agents.policy_agent import policy_check
from src.agents.po_agent import create_po
from src.agents.notify_agent import notify
from src.utils.logger import logger
from src.utils.config import ALLOYDB_TABLESCHEMA


@dataclass
class ReplenishmentPlan:
    """
    Container for a single store–SKU replenishment recommendation.

    Attributes:
        store_id (int): Identifier for the store where stocking is evaluated.
        sku (str): Stock keeping unit under consideration.
        horizon_days (int): Forecast horizon in days used to determine demand.
        forecast_mean (float): Mean demand estimate for the horizon.
        forecast_ci (Tuple[float, float]): Confidence interval bounds (low, high).
        method (str): Forecasting method or model label returned by Demand Agent.
        net_position (float): Current inventory position (on-hand + in-transit).
        safety_stock (float): Target buffer stock to protect against variability.
        needed (float): Calculated total quantity needed (can be 0 if sufficient).
        supplier_choice (Dict[str, Any]): Selected supplier proposal details.
        recommended_qty (int): Rounded order quantity recommended for the PO.
        policy_citations (List[Dict[str, str]]): Policy references supporting the decision.
        status (str): Lifecycle status (e.g., "PO created", "Rejected or zero qty").
        po_id (int | None): Created purchase order identifier if applicable; None otherwise.
    """

    store_id: int
    sku: str
    horizon_days: int
    forecast_mean: float
    forecast_ci: Tuple[float, float]
    method: str
    net_position: float
    safety_stock: float
    needed: float
    supplier_choice: Dict[str, Any]
    recommended_qty: int
    policy_citations: List[Dict[str, str]]
    status: str
    po_id: int | None = None


def recent_7_day_avg(engine, sku: str, store_id: int) -> float:
    """
    Computes a simple 7-day average of quantity sold for a given store–SKU.

    Args:
        engine: SQLAlchemy engine used to execute the query.
        sku (str): Product SKU for which demand is averaged.
        store_id (int): Store identifier to filter transactions.

    Returns:
        float: Average quantity per day over the last 7 days. Returns 0.0 when
        there is no transaction data for the given store–SKU.
    """
    # Query: aggregate quantities by day, then take the latest 7 days.
    query = text(
        f"""
        SELECT DATE(order_ts) AS day, SUM(quantity)::float AS qty
        FROM {ALLOYDB_TABLESCHEMA}.transactions
        WHERE store_id = :store_id AND sku = :sku
        GROUP BY DATE(order_ts)
        ORDER BY day DESC
        LIMIT 7;
    """
    )

    # Open a connection and fetch the last 7 daily aggregates.
    # Note: returns a list of rows, driver may yield dict-like or tuple-like rows.
    with engine.connect() as connection:
        rows = connection.execute(query, {"store_id": store_id, "sku": sku}).fetchall()

    # If nothing is found, signal the fallback and return 0.0.
    if not rows:
        print(f"⚠️ No transaction data found for SKU {sku} at store {store_id}")
        return 0.0

    # Sum the daily quantities, accounting for row type (dict vs. tuple).
    total_qty = sum(row["qty"] if isinstance(row, dict) else row[1] for row in rows)

    # Daily average over 7 days; guards upstream logic against division nuances.
    return total_qty / 7.0


async def recommend_replenishment(
    broadcast, engine, store_id: int, sku: str, horizon_days: int = 14
) -> Dict[str, Any]:
    """
    Orchestrates demand, inventory, supplier, policy, notification, and PO creation
    to produce a replenishment recommendation for a specific store–SKU.

    Workflow:
        1) Demand Agent: forecast mean & CI over `horizon_days`.
        2) Inventory Agent: snapshot on-hand, in-transit, safety stock, reorder point.
        3) Compute needed quantity based on forecast and inventory position.
        4) Supplier Agent: gather feasible proposals (MOQ, cost, lead time, preference).
        5) Policy Agent: apply caps/constraints; collect citations.
        6) Notify Agent: request approval; proceed only if approved.
        7) PO Agent: create a purchase order for the chosen supplier if approved.

    Args:
        broadcast: Messaging or orchestration handle used by agents.
        engine: SQLAlchemy engine for any data lookups required during fallback.
        store_id (int): Store identifier for the recommendation.
        sku (str): Product SKU for which replenishment is evaluated.
        horizon_days (int, optional): Forecast horizon in days; defaults to 14.

    Returns:
        Dict[str, Any]: Either a serialized `ReplenishmentPlan` (as a dict) or an
        error payload with status, sku, and message describing the failure path.
    """

    # 1) Demand Agent — request horizon forecast for store–SKU.
    fc = await forecast_sku_store(broadcast, engine, store_id, sku, horizon_days)
    logger.info(f"Demand Agent workflow completed, results : {fc}")

    # Extract demand statistics safely with defaults for missing fields.
    forecast_mean = float(fc.get("mean") or 0.0)
    forecast_ci = tuple(fc.get("ci") or (0.0, 0.0))
    method = fc.get("method", "unknown")

    # 2) Inventory Agent — fetch inventory snapshot and planning parameters.
    inv = await inventory_snapshot(broadcast, engine, store_id, sku)
    logger.info(f"Inventory Agent workflow completed, results : {inv}")

    on_hand = float(inv.get("on_hand") or 0.0)
    in_transit = float(inv.get("in_transit") or 0.0)
    safety_stock = float(inv.get("safety_stock") or 0.0)
    reorder_point = float(inv.get("reorder_point") or 0.0)
    # Net position is the available + incoming stock used for shortfall checks.
    net_position = on_hand + in_transit

    # Initialize `needed` to zero; will be derived from forecast + policy buffers.
    needed = 0.0

    # Fallback path: if forecasting failed or returned zero, attempt a 7-day average.
    if forecast_mean == 0.0:
        forecast_mean = recent_7_day_avg(engine, sku, store_id)
        print(f"⚠️ Fallback to 7-day average for SKU {sku}: {forecast_mean}")

        # If fallback also yields zero, use threshold-based overrides:
        # - If net position is below reorder point, order up to the point.
        # - Else if below safety stock, top up to safety stock.
        # - Else no replenishment needed.
        if forecast_mean == 0.0:
            if net_position < reorder_point:
                needed = reorder_point - net_position
                print(
                    f"⚠️ Reorder point override for SKU {sku}: net_position {net_position} < reorder_point {reorder_point}"
                )
            elif net_position < safety_stock:
                needed = safety_stock - net_position
                print(
                    f"⚠️ Manual override triggered for SKU {sku}: net_position {net_position} < safety_stock {safety_stock}"
                )
            else:
                needed = max(
                    0.0, forecast_mean * horizon_days + safety_stock - net_position
                )
        else:
            # Forecast available via fallback: compute horizon demand then shortfall.
            demand_horizon = forecast_mean * horizon_days
            needed = max(0.0, demand_horizon + safety_stock - net_position)
    else:
        # Normal path using provided forecast.
        demand_horizon = forecast_mean * horizon_days
        needed = max(0.0, demand_horizon + safety_stock - net_position)

    # 3) Supplier Agent — retrieve proposals satisfying MOQ, cost, lead time, etc.
    options = await supplier_options(broadcast, engine, sku)
    logger.info(f"Supplier Agent workflow completed, results : {options}")

    # If no options exist, we cannot proceed to replenishment.
    if not options:
        return {
            "error": {
                "status": "no_replenishment",
                "sku": sku,
                "message": "Replenishment not generated because no supplier proposal met constraints: lead time exceeded window, MOQ too high for forecast, price above threshold, or supplier not eligible for this store.",
            }
        }

    # 4) Policy Agent — derive constraints (e.g., maximum single PO value) and citations.
    constraints, citations = await policy_check(
        broadcast, engine, query=f"Caps & substitution for {sku}"
    )
    logger.info(f"Policy Agent workflow completed, results : {constraints},{citations}")

    # Cap to protect against budget or risk on a single PO.
    max_single_po = float(constraints.get("max_single_po") or 25000)

    # Build candidate proposals that respect MOQ and PO caps.
    proposals = []

    for o in options:
        moq = int(o.get("moq") or 0)
        cost = float(o.get("cost") or 0.0)
        lead = int(o.get("lead_time_days") or 0)

        # Skip suppliers if no demand is expected.
        if needed <= 0:
            print(f"❌ Skipping {o['name']} for SKU {sku}: No demand forecasted.")
            continue

        # Enforce MOQ: if need is below supplier's threshold, reject.
        if needed < moq:
            print(f"❌ Rejected {o['name']} for SKU {sku}: Needed {needed} < MOQ {moq}")
            continue

        # Initial quantity: respect MOQ, then round need up to next integer.
        qty = max(moq, ceil(needed))
        value = qty * cost

        # Apply PO value cap; adjust quantity down to fit the cap.
        if value > max_single_po:
            qty = int(max_single_po // cost)
            value = qty * cost
            print(
                f"⚠️ Adjusted qty for {o['name']} due to PO cap: New qty {qty}, value {value}"
            )

        # If the cap drove qty to zero (e.g., cost > cap), skip this supplier.
        if qty <= 0:
            print(f"❌ Skipping {o['name']} for SKU {sku}: Calculated qty is zero.")
            continue

        # Record a normalized proposal for ranking.
        proposals.append(
            {
                "supplier_id": o["supplier_id"],
                "supplier": o["name"],
                "preferred": bool(o.get("preferred")),
                "lead_time_days": lead,
                "unit_cost": cost,
                "qty": qty,
                "po_value": value,
            }
        )

    # If all proposals were filtered out by constraints, return an actionable error.
    if not proposals:
        return {
            "error": {
                "status": "no_replenishment",
                "sku": sku,
                "message": "Replenishment not generated because no supplier proposal met constraints: lead time exceeded window, MOQ too high for forecast, price above threshold, or supplier not eligible for this store.",
            }
        }

    # Sort by (non-preferred last), shortest lead time, then lowest unit cost.
    proposals.sort(
        key=lambda r: (not r["preferred"], r["lead_time_days"], r["unit_cost"])
    )

    # Choose the top-ranked supplier proposal.
    chosen = proposals[0]

    # Prepare a compact summary for the approval workflow.
    summary = {
        "store_id": store_id,
        "sku": sku,
        "forecast_mean": forecast_mean,
        "method": method,
        "net_position": net_position,
        "safety_stock": safety_stock,
        "needed": needed,
        "recommended_qty": chosen["qty"],
        "supplier": chosen["supplier"],
        "unit_cost": chosen["unit_cost"],
        "policy_citations": citations,
    }

    # 5) Notify Agent — request approval from an approver; handle communication failures.
    try:
        approval = await notify(broadcast, summary)
        logger.info(f"Notify Agent workflow completed, results : {approval}")
    except Exception as e:
        return {"error": f"Notification failed: {str(e)}"}

    # Default status when not approved or quantity is zero.
    po_id = None
    status = "Rejected or zero qty"

    # 6) If approved and quantity is positive, create the PO with the chosen supplier.
    if approval.get("approved") and chosen["qty"] > 0:
        try:
            po_id = await create_po(
                broadcast,
                engine,
                chosen["supplier_id"],
                [
                    {
                        "sku": sku,
                        "qty": chosen["qty"],
                        "unit_cost": chosen["unit_cost"],
                        "lead_time_days": chosen["lead_time_days"],
                    }
                ],
                created_by=approval.get("approver", "agent"),
            )
            logger.info(f"PO Agent workflow completed, results : {po_id}")

            status = "PO created"
        except Exception as e:
            return {"error": f"PO creation failed: {str(e)}"}

    # Build the final structured recommendation object and return its dict view.
    result = ReplenishmentPlan(
        store_id,
        sku,
        horizon_days,
        forecast_mean,
        forecast_ci,
        method,
        net_position,
        safety_stock,
        needed,
        chosen,
        chosen["qty"],
        citations,
        status,
        po_id,
    )

    # Return a plain dictionary so downstream consumers (e.g., UI/JSON) can serialize easily.
    return result.__dict__
