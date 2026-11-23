import re
from typing import Any, Dict, List, Tuple
from config import RATING_THRESHOLD
__all__ = ["_normalize_filters", "_build_where_clause", "_compose_where_clause"]

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


_ALLOWED_COLUMNS = {c.lower(): c for c in (
    "id", "year", "discount", "unitPrice", "finalPrice", "rating", "gender", "masterCategory",
    "subCategory", "articleType", "baseColour", "season", "usage", "productDisplayName",
    "brand", "stockCode", "stockStatus", "combined_description")}
_KEYWORDS = frozenset({"and", "or", "not", "in", "like", "ilike", "between", "is", "null"})
_TOKEN_RE = re.compile(r"\s*(?:'((?:[^']|'')*)'|(\d{1,18}(?:\.\d{1,18})?)(?![\w.])|([A-Za-z_]\w*)|(<>|!=|<=|>=|[=<>(),]))", re.ASCII)


def _compile_sql_constraints(constraints: Any) -> Tuple[str, Dict[str, Any]]:
    """Rebuilds LLM sql_constraints from allowlisted tokens; every literal becomes a bind param."""
    if constraints is None or (isinstance(constraints, str) and constraints.strip().lower() in ("", "none", "null")):
        return "", {}
    if not isinstance(constraints, str) or len(constraints) > 1024:
        raise ValueError("Invalid sql_constraints")
    text, out, params, depth, pos = constraints.strip(), [], {}, 0, 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        string, number, word, sym = m.groups() if m else (None,) * 4
        if string is not None or number is not None:
            name = f"llm_constraint_{len(params)}"
            params[name] = string.replace("''", "'") if string is not None else float(number) if "." in number else int(number)
            out.append(f":{name}")
        elif word is not None and (word.lower() in _ALLOWED_COLUMNS or word.lower() in _KEYWORDS):
            out.append(_ALLOWED_COLUMNS.get(word.lower(), word.upper()))
        elif sym is not None and 0 <= depth + (sym == "(") - (sym == ")") <= 5:
            depth += (sym == "(") - (sym == ")")
            out.append(sym)
        else:
            break
        pos = m.end()
    if pos < len(text) or depth:
        raise ValueError(f"Invalid sql_constraints: {text[:200]!r}")
    return " ".join(out), params


def _compose_where_clause(filters: Any, filtered_search: Any) -> Tuple[str, Dict[str, Any]]:
    """Combines UI filters with parameterized LLM sql_constraints."""
    where_sql, params = _build_where_clause(_normalize_filters(filters))
    llm_sql, llm_params = _compile_sql_constraints(filtered_search)
    if llm_sql:
        where_sql = f"{where_sql} AND ({llm_sql})" if where_sql else f"WHERE {llm_sql}"
    return where_sql, {**params, **llm_params}
