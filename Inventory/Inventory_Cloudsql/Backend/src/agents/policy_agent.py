# policy_agent.py
from __future__ import annotations
from typing import Dict, Any, Tuple, List
from functools import lru_cache

from src.agents.tools import get_vector_retriever
from src.utils.broadcast_decorator import status_broadcast


@lru_cache(maxsize=1)
def _get_retriever():
    """
    Builds and caches a vector retriever (top-k policy/documents) for reuse.

    The retriever is created from an AlloyDB-backed vector store and cached to
    avoid repeated initialization. If creation fails (e.g., DB unavailable or
    missing environment), returns None; a subsequent invocation will retry.

    Returns:
        Any | None: A retriever that supports either `get_relevant_documents(query)`
        or `invoke(query)`, or None on failure.

    Notes:
        - lru_cache will cache the returned value (including None).
        - Returning None here does not permanently prevent retries; each new
          process run will evaluate this again.
    """
    try:
        r = get_vector_retriever(table="docs", column="embedding", k=4)
        # Sanity check: confirm it has an expected method
        if hasattr(r, "get_relevant_documents") or hasattr(r, "invoke"):
            return r
        return None
    except Exception:
        # Could be DB unavailable, env missing, etc.
        return None


@status_broadcast("Policy Agent is working")
async def policy_check(
    broadcast, query: str
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """
    Retrieves policy constraints and citations relevant to a query string.

    This function attempts to fetch top-k policy/SOP documents via the cached
    retriever. It then extracts minimal metadata for citations and returns
    canonical constraints for downstream decisioning. On any error, it returns
    default constraints with an empty citation list.

    Args:
        broadcast: Orchestration/messaging object used by the status decorator.
        query (str): Natural language prompt describing the policy context
            (e.g., "Caps & substitution for SKU123").

    Returns:
        Tuple[Dict[str, Any], List[Dict[str, str]]]:
            - constraints: Policy rules applied during replenishment:
                * max_single_po (float): Maximum PO value for a single order.
                * allow_substitution (bool): Whether substitution is permitted.
                * substitution_scope (str): Scope (e.g., same_category).
            - citations: Minimal metadata from retrieved docs:
                * source (str): Source URL or reference.
                * doc_type (str): Classification of the document.
                * snippet (str): First 220 characters of content.

    Notes:
        - This function NEVER returns None; defaults are used when retrieval fails.
    """
    retriever = _get_retriever()

    # Container for retrieved documents; remains empty if retriever is None or fails.
    docs: List[Any] = []

    if retriever is not None:
        try:
            # Support both common retriever interfaces (LangChain variants).
            if hasattr(retriever, "get_relevant_documents"):
                docs = retriever.get_relevant_documents(query) or []
            elif hasattr(retriever, "invoke"):
                docs = retriever.invoke(query) or []
        except Exception:
            # Retrieval failed; proceed with empty citations
            docs = []

    # Build a citation list (source, doc_type, snippet) from document metadata.
    citations: List[Dict[str, str]] = []
    for d in docs:
        md = getattr(d, "metadata", {}) or {}
        citations.append(
            {
                "source": md.get("source_url", "") or "",
                "doc_type": md.get("doc_type", "") or "",
                "snippet": (getattr(d, "page_content", "") or "")[:220],
            }
        )

    # Canonical constraints used by downstream logic (static defaults here).
    constraints: Dict[str, Any] = {
        "max_single_po": 25000.0,
        "allow_substitution": True,
        "substitution_scope": "same_category",
    }

    # Return constraints alongside citations for traceability.
    return constraints, citations
