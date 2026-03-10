from typing import Any, Dict, List, Tuple
from config import RATING_THRESHOLD
__all__ = ["_normalize_filters", "_build_where_clause"]

# -------------------------------------------------------------------
# Column configuration (CHANGE THESE to match your actual schema)
# -------------------------------------------------------------------
COLUMN_MAP = {
    "category": 'masterCategory',      
    "brand": 'brand',
    "rating": 'rating',
    "price": 'finalPrice',       
}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _normalize_filters(filters: Any) -> Dict[str, Any]:
    """
    Accepts:
      - None / {} / "NIL"
      - {"filter": {...}}
      - {...} (already inner dict)
    Returns inner filter dict.
    """
    if not filters or filters == "NIL":
        return {}

    if isinstance(filters, dict) and "filter" in filters and isinstance(filters["filter"], dict):
        return filters["filter"]

    if isinstance(filters, dict):
        return filters

    return {}


def _build_where_clause(filters_dict: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """
    Build a safe WHERE clause for top_matches using bind parameters.
    Returns: (where_sql, params)

    Supported filters:
      - category: exact match
      - brand: exact match
      - rating: minimum rating (>=)
      - price: min/max range on COLUMN_MAP["price"]
    """
    where_parts: List[str] = []
    params: Dict[str, Any] = {}

    # category
    category = filters_dict.get("category")
    if category is not None and str(category).strip():
        col = COLUMN_MAP["category"]
        where_parts.append(f"{col} = :category")
        params["category"] = str(category).strip()

    # brand
    brand = filters_dict.get("brand")
    if brand is not None and str(brand).strip():
        col = COLUMN_MAP["brand"]
        where_parts.append(f"{col} = :brand")
        params["brand"] = str(brand).strip()

    # rating min
    rating_min = filters_dict.get("rating")
    if rating_min is not None and str(rating_min).strip():
        col = COLUMN_MAP["rating"]
        if rating_min == RATING_THRESHOLD:
            where_parts.append(f"{col} = :rating_min")
        else:
            where_parts.append(f"{col} >= :rating_min")
        params["rating_min"] = float(rating_min)

    # price range
    price_obj = filters_dict.get("price") or {}
    if isinstance(price_obj, dict):
        pmin = price_obj.get("min")
        pmax = price_obj.get("max")
        price_col = COLUMN_MAP["price"]

        if pmin is not None and str(pmin).strip():
            where_parts.append(f"{price_col} >= :price_min")
            params["price_min"] = float(pmin)

        if pmax is not None and str(pmax).strip():
            where_parts.append(f"{price_col} <= :price_max")
            params["price_max"] = float(pmax)

    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    return where_sql, params
