from __future__ import annotations
from typing import Dict, Any
from src.utils.broadcast_decorator import status_broadcast


@status_broadcast("Notify Agent is working")
async def notify(broadcast, summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends a notification summarizing the replenishment recommendation and
    simulates an approval response.

    This function prints the approval summary to the console and returns a
    hardcoded approval payload. In a production scenario, this would integrate
    with an external approval workflow or messaging system.

    Args:
        broadcast: Orchestration or messaging object used by the status decorator.
        summary (Dict[str, Any]): Key-value pairs summarizing the replenishment
            recommendation (e.g., store_id, SKU, forecast, supplier details).

    Returns:
        Dict[str, Any]: Approval response containing:
            - approved (bool): Indicates whether the recommendation was approved.
            - approver (str): Identifier of the approver (currently hardcoded).
    """

    # -------------------------------------------------------------------------
    # Display the approval summary for visibility.
    # Each key-value pair from the recommendation summary is printed.
    # -------------------------------------------------------------------------
    print("=== APPROVAL SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print("========================")
    return {"approved": True, "approver": "planner@retail.example"}
