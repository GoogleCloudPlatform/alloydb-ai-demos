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
from src.utils.config import CLOUDSQL_TABLESCHEMA


@dataclass
class ReplenishmentPlan:
    """
    Structured payload capturing a single store–SKU replenishment recommendation.

    Attributes:
        store_id (int): Store identifier for which the plan applies.
        sku (str): Target SKU.
        horizon_days (int): Forecast horizon used to compute demand.
        forecast_mean (float): Mean demand estimate over the horizon.
        forecast_ci (Tuple[float, float]): CI bounds (low, high) from forecasting.
        method (str): Forecasting method (e.g., 'prophet', 'moving-average').
        net_position (float): on_hand + in_transit at the time of planning.
        safety_stock (float): Buffer stock target.
        needed (float): Calculated shortfall to cover horizon + safety stock.
        supplier_choice (Dict[str, Any]): Selected supplier proposal details.
        recommended_qty (int): Rounded recommended order quantity.
        policy_citations (List[Dict[str, str]]): Supporting policy references.
        status (str): Plan status (e.g., 'PO created', 'Rejected or zero qty').
        po_id (int | None): Created PO identifier, if any.
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
    Computes the average daily quantity sold over the last 7 days for a store–SKU.

    Args:
        engine: SQLAlchemy engine used to execute the query.
        sku (str): Target product SKU.
        store_id (int): Store identifier.

    Returns:
        float: 7-day average quantity; returns 0.0 if no data is found.
    """
    # Aggregate by day and limit to the most recent seven days.
    query = text(
        f"""
        SELECT DATE(order_ts) AS day, SUM(quantity)::float AS qty
        FROM {CLOUDSQL_TABLESCHEMA}.transactions
        WHERE store_id = :store_id AND sku = :sku
        GROUP BY DATE(order_ts)
        ORDER BY day DESC
        LIMIT 7;
    """
    )

    # Execute query and fetch results.
    # Note: some drivers return dict-like rows, others tuples; handle both.
    # engine = alloydb_client.create_engine()
    # engine = alloydb_client.alloydb_engine
    with engine.connect() as connection:
        rows = connection.execute(query, {"store_id": store_id, "sku": sku}).fetchall()

    if not rows:
        print(f"⚠️ No transaction data found for SKU {sku} at store {store_id}")
        return 0.0
    total_qty = sum(row["qty"] if isinstance(row, dict) else row[1] for row in rows)
    return total_qty / 7.0


async def recommend_replenishment(
    broadcast, engine, store_id: int, sku: str, horizon_days: int = 14
) -> Dict[str, Any]:
    """
    Orchestrates the end-to-end replenishment decision for a store–SKU:
      1) Demand forecast (mean, CI, method).
      2) Inventory snapshot (on_hand, in_transit, safety_stock, reorder_point).
      3) Shortfall computation → needed quantity.
      4) Supplier option filtering and ranking (MOQ, lead time, unit cost, PO cap).
      5) Policy constraints retrieval and citations.
      6) Approval notification.
      7) Purchase order creation (if approved).

    Args:
        broadcast: Orchestration/messaging object used by agents.
        engine: SQLAlchemy engine for DB operations/fallbacks.
        store_id (int): Store identifier.
        sku (str): SKU to evaluate.
        horizon_days (int, optional): Forecast horizon in days. Defaults to 14.

    Returns:
        Dict[str, Any]: Serialized `ReplenishmentPlan` dictionary, or an error payload
        when constraints eliminate all supplier options or downstream steps fail.
    """
    # 1) Demand forecast via Demand Agent.
    fc = await forecast_sku_store(broadcast, engine, store_id, sku, horizon_days)
    logger.info(f"Demand Agent workflow completed, results : {fc}")

    forecast_mean = float(fc.get("mean") or 0.0)
    forecast_ci = tuple(fc.get("ci") or (0.0, 0.0))
    method = fc.get("method", "unknown")

    # 2) Inventory snapshot via Inventory Agent.
    inv = await inventory_snapshot(broadcast, engine, store_id, sku)
    logger.info(f"Inventory Agent workflow completed, results : {inv}")

    on_hand = float(inv.get("on_hand") or 0.0)
    in_transit = float(inv.get("in_transit") or 0.0)
    safety_stock = float(inv.get("safety_stock") or 0.0)
    reorder_point = float(inv.get("reorder_point") or 0.0)

    # Current availability including inbound.
    net_position = on_hand + in_transit

    # Shortfall (needed) initialization; will be computed below.
    needed = 0.0

    # 3) Fallbacks and shortfall computation.
    if forecast_mean == 0.0:
        forecast_mean = recent_7_day_avg(engine, sku, store_id)
        print(f"⚠️ Fallback to 7-day average for SKU {sku}: {forecast_mean}")

        if forecast_mean == 0.0:
            # Threshold-based overrides when demand is unknown.
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
            demand_horizon = forecast_mean * horizon_days
            needed = max(0.0, demand_horizon + safety_stock - net_position)
    else:
        demand_horizon = forecast_mean * horizon_days
        needed = max(0.0, demand_horizon + safety_stock - net_position)

    # 4) Supplier options via Supplier Agent.
    options = await supplier_options(broadcast, engine, sku)
    logger.info(f"Supplier Agent workflow completed, results : {options}")

    # If no options are available, return an actionable error
    if not options:
        return {
            "error": {
                "status": "no_replenishment",
                "sku": sku,
                "message": "Replenishment not generated because no supplier proposal met constraints: lead time exceeded window, MOQ too high for forecast, price above threshold, or supplier not eligible for this store.",
            }
        }

    # 5) Policy constraints and citations via Policy Agent.
    constraints, citations = await policy_check(
        broadcast, query=f"Caps & substitution for {sku}"
    )
    logger.info(f"Policy Agent workflow completed, results : {constraints},{citations}")

    max_single_po = float(constraints.get("max_single_po") or 25000)
    proposals = []

    # Build proposals that respect MOQ and PO caps.
    for o in options:
        moq = int(o.get("moq") or 0)
        cost = float(o.get("cost") or 0.0)
        lead = int(o.get("lead_time_days") or 0)

        if needed <= 0:
            print(f"❌ Skipping {o['name']} for SKU {sku}: No demand forecasted.")
            continue

        if needed < moq:
            print(f"❌ Rejected {o['name']} for SKU {sku}: Needed {needed} < MOQ {moq}")
            continue

        qty = max(moq, ceil(needed))
        value = qty * cost

        if value > max_single_po:
            qty = int(max_single_po // cost)
            value = qty * cost
            print(
                f"⚠️ Adjusted qty for {o['name']} due to PO cap: New qty {qty}, value {value}"
            )

        if qty <= 0:
            print(f"❌ Skipping {o['name']} for SKU {sku}: Calculated qty is zero.")
            continue

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

    # If constraints eliminate all proposals, return error payload.
    if not proposals:
        return {
            "error": {
                "status": "no_replenishment",
                "sku": sku,
                "message": "Replenishment not generated because no supplier proposal met constraints: lead time exceeded window, MOQ too high for forecast, price above threshold, or supplier not eligible for this store.",
            }
        }

    # Rank by preference (preferred first), shortest lead time, lowest unit cost.
    proposals.sort(
        key=lambda r: (not r["preferred"], r["lead_time_days"], r["unit_cost"])
    )
    chosen = proposals[0]

    # Summarize plan for approval (display/notify).
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

    # 6) Notify approver and obtain approval decision.
    try:
        approval = await notify(broadcast, summary)
        logger.info(f"Notify Agent workflow completed, results : {approval}")
    except Exception as e:
        return {"error": f"Notification failed: {str(e)}"}

    # Default status before PO creation.
    po_id = None
    status = "Rejected or zero qty"

    # 7) If approved and quantity positive, create PO with chosen supplier.
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

    # Assemble final recommendation payload and return as a plain dict.
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
    return result.__dict__
