import re
from typing import Any, Dict, List, Tuple
from config import RATING_THRESHOLD

# -------------------------------------------------------------------
# Column configuration (CHANGE THESE to match your actual schema)
# -------------------------------------------------------------------
COLUMN_MAP = {
    "category": "masterCategory",
    "brand": "brand",
    "rating": "rating",
    "price": "finalPrice",
}


def merge_where_clauses(filters_where_sql: str, generated_sql: str) -> str:
    """
    Merge filters_where_sql (starts with 'WHERE ...' or empty) into generated_sql.
    - If generated_sql already has WHERE: merge with AND using parentheses.
    - If not: append filters WHERE.
    This does not parse SQL deeply, but is robust for common single-statement SELECTs.
    """

    # Normalize whitespace
    fws = (filters_where_sql or "").strip()
    gsql = (generated_sql or "").strip().rstrip(";")

    if not fws:
        return gsql + ";"

    # Extract filter condition without leading WHERE
    f_cond = re.sub(r"^\s*WHERE\s+", "", fws, flags=re.IGNORECASE).strip()
    if not f_cond:
        return gsql + ";"

    # Detect WHERE in generated SQL (case-insensitive)
    # We split only on the FIRST WHERE occurrence.
    m = re.search(r"\bWHERE\b", gsql, flags=re.IGNORECASE)
    if not m:
        # No WHERE: append filter WHERE at end, but before ORDER BY / GROUP BY / LIMIT if present
        # We'll insert the WHERE before these clauses if they exist.
        insert_points = ["ORDER BY", "GROUP BY", "LIMIT", "OFFSET", "FETCH", "FOR"]
        idx = len(gsql)

        upper = gsql.upper()
        for kw in insert_points:
            kw_idx = upper.find(kw)
            if kw_idx != -1:
                idx = min(idx, kw_idx)

        return (
            gsql[:idx].rstrip() + f" WHERE ({f_cond}) " + gsql[idx:].lstrip()
        ).rstrip() + ";"

    # Has WHERE: split into head + existing where + tail
    head = gsql[: m.start()].rstrip()
    rest = gsql[m.end() :].lstrip()  # everything after WHERE

    # Now, rest contains: "<where_conditions> <maybe ORDER BY ...>"
    # We want to isolate existing conditions from trailing clauses.
    clause_keywords = [
        " ORDER BY ",
        " GROUP BY ",
        " LIMIT ",
        " OFFSET ",
        " FETCH ",
        " FOR ",
    ]
    upper_rest = " " + rest.upper() + " "
    cut = len(rest)

    for kw in clause_keywords:
        kw_idx = upper_rest.find(kw)
        if kw_idx != -1:
            # adjust because we added leading/trailing spaces
            cut = min(cut, max(0, kw_idx - 1))

    existing_cond = rest[:cut].strip()
    tail = rest[cut:].strip()

    merged_where = f"WHERE ({f_cond}) AND ({existing_cond})"
    merged_sql = f"{head} {merged_where}"
    if tail:
        merged_sql += f" {tail}"
    return merged_sql.rstrip() + ";"


def merge_filter_where(sql: str, where_sql: str) -> str:
    """
    Merge a filter where_sql (like 'WHERE a=:a AND b=:b') into sql.

    This version intentionally does NOT handle any quoting rules.
    It only tracks parentheses nesting to avoid absorbing ') SELECT ...'
    into an inner WHERE (e.g., within a CTE).

    Rules:
    - If sql has WHERE -> WHERE (filter) AND (existing)
    - If not -> add WHERE (filter) before ORDER BY/GROUP BY/LIMIT...
    """
    sql = (sql or "").strip().rstrip(";")
    where_sql = (where_sql or "").strip()

    if not sql:
        return ";"
    if not where_sql:
        return sql + ";"

    # remove leading WHERE from filter clause
    filter_cond = re.sub(r"^\s*WHERE\s+", "", where_sql, flags=re.IGNORECASE).strip()
    if not filter_cond:
        return sql + ";"

    clause_keywords = [
        "ORDER BY",
        "GROUP BY",
        "HAVING",
        "LIMIT",
        "OFFSET",
        "FETCH",
        "FOR",
        "UNION",
        "INTERSECT",
        "EXCEPT",
    ]

    def _split_existing_cond_and_tail(rest: str) -> tuple[str, str]:
        """
        Split everything after WHERE into:
          existing_cond, tail

        Boundary rules (TOP-LEVEL only):
        - stop at ')' when nesting level == 0  (CTE/subquery closes)
        - stop at clause keyword (ORDER BY/LIMIT/...) when nesting level == 0
        """
        i = 0
        level = 0
        upper_rest = rest.upper()

        while i < len(rest):
            ch = rest[i]

            if ch == "(":
                level += 1
                i += 1
                continue

            if ch == ")":
                if level == 0:
                    return rest[:i].strip(), rest[i:].strip()
                level -= 1
                i += 1
                continue

            if level == 0:
                for kw in clause_keywords:
                    if upper_rest.startswith(kw, i):
                        prev_ok = (i == 0) or (
                            not (rest[i - 1].isalnum() or rest[i - 1] == "_")
                        )
                        if prev_ok:
                            return rest[:i].strip(), rest[i:].strip()

            i += 1

        return rest.strip(), ""

    def _first_top_level_clause_pos(s: str) -> int:
        """
        Find earliest top-level position of a trailing clause keyword.
        Used when original SQL has no WHERE: insert filter WHERE before tail.
        """
        i = 0
        level = 0
        upper_s = s.upper()

        while i < len(s):
            ch = s[i]

            if ch == "(":
                level += 1
                i += 1
                continue
            if ch == ")":
                if level > 0:
                    level -= 1
                i += 1
                continue

            if level == 0:
                for kw in clause_keywords:
                    if upper_s.startswith(kw, i):
                        prev_ok = (i == 0) or (
                            not (s[i - 1].isalnum() or s[i - 1] == "_")
                        )
                        if prev_ok:
                            return i

            i += 1

        return len(s)

    # Find first WHERE
    m = re.search(r"\bWHERE\b", sql, flags=re.IGNORECASE)

    if not m:
        # Insert WHERE before trailing clauses if any
        cut = _first_top_level_clause_pos(sql)
        head = sql[:cut].rstrip()
        tail = sql[cut:].lstrip()
        merged = f"{head} WHERE ({filter_cond})"
        if tail:
            merged += f" {tail}"
        return merged.rstrip() + ";"

    # SQL already has WHERE: merge conditions safely
    head = sql[: m.start()].rstrip()
    after_where = sql[m.end() :].lstrip()

    existing_cond, tail = _split_existing_cond_and_tail(after_where)

    if existing_cond:
        merged = f"{head} WHERE ({filter_cond}) AND ({existing_cond})"
    else:
        merged = f"{head} WHERE ({filter_cond})"

    if tail:
        merged += f" {tail}"

    return merged.rstrip() + ";"


def normalize_filters(filters: Any) -> Dict[str, Any]:
    """
    Accepts:
      - None / {} / "NIL"
      - {"filter": {...}}
      - {...} (already inner dict)
    Returns inner filter dict.
    """
    if not filters or filters == "NIL":
        return {}

    if (
        isinstance(filters, dict)
        and "filter" in filters
        and isinstance(filters["filter"], dict)
    ):
        return filters["filter"]

    if isinstance(filters, dict):
        return filters

    return {}


def build_where_clause(filters_dict: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
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


def remove_single_line_comments(sql: str) -> str:
    cleaned_lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        # Skip lines that start with single-line comment
        if stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)
