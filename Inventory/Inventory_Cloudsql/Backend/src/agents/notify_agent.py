from __future__ import annotations
from typing import Dict, Any
from src.utils.broadcast_decorator import status_broadcast


@status_broadcast("Notify Agent is working")
async def notify(broadcast, summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends/prints a summary of the replenishment recommendation and returns a
    simulated approval response.

    This implementation simply logs the key-value pairs of the summary to the
    console and returns a hard-coded approval. In production, this would be
    replaced by an integration with an approval workflow or messaging system
    (e.g., email, chat, or ERP/WMS approval endpoint).

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        summary (Dict[str, Any]): Consolidated data for approval context:
            - store_id, sku, forecast_mean, method, net_position, safety_stock,
              needed, recommended_qty, supplier, unit_cost, policy_citations.

    Returns:
        Dict[str, Any]: Approval payload containing:
            - approved (bool): Whether the recommendation is approved.
            - approver (str): Identifier of the approving party (static here).
    """

    # -------------------------------------------------------------------------
    # Print the approval summary for visibility. Each item is displayed as
    # "key: value" to make it easy to audit and verify inputs.
    # -------------------------------------------------------------------------
    print("=== APPROVAL SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print("========================")
    return {"approved": True, "approver": "planner@retail.example"}
