"""SQL safety guardrails for the AlloyDB Product-Finder backend.

Provides a single cohesive module encapsulating:
- Strict SQL identifier, search text, and prompt template validation.
- DDL-aware catalog column typing and literal coercion for pg8000 RENDER_CASTS.
- Single-pass PostgreSQL-aware SQL tokenization (comment/escape/control hygiene).
- Recursive-descent compilation of LLM-emitted WHERE constraints into typed binds.
- Single-parse, single-coercion, token-rebuilt single-table SELECT validation.
- Scoped read-only transaction execution with AUTOCOMMIT detection and optional timeout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from decimal import Decimal, InvalidOperation
import re
from types import MappingProxyType
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import BindParameter, TextClause
from sqlalchemy.sql.type_api import TypeEngine
import sqlparse

__all__ = (
    "CATALOG_COLUMN_TYPES",
    "UI_SELECT_COLUMNS",
    "UnsafeSQLError",
    "build_safe_nltosql_query",
    "clean_search_text",
    "coerce_column_literal",
    "combine_where_clauses",
    "compile_sql_constraints",
    "empty_search_result",
    "execute_readonly",
    "format_display_sql",
    "tokenize_sql",
    "validate_question_template",
    "validate_sql_identifier",
)


class UnsafeSQLError(ValueError):
    """Input SQL, identifier, filter, or DB execution state violates policy."""


# Canonical DDL columns for alloydb_usecase.fashion_products (19 columns).
# Excludes combined_description_embedding (VECTOR(768)) and PG system columns.
CATALOG_COLUMN_TYPES: Mapping[str, str] = MappingProxyType({
    "id": "int",
    "year": "int",
    "discount": "int",
    "unitprice": "numeric",
    "finalprice": "numeric",
    "rating": "numeric",
    "gender": "str",
    "mastercategory": "str",
    "subcategory": "str",
    "articletype": "str",
    "basecolour": "str",
    "season": "str",
    "usage": "str",
    "productdisplayname": "str",
    "brand": "str",
    "link": "str",
    "stockcode": "str",
    "stockstatus": "str",
    "combined_description": "str",
})

# Exact 6 UI product card columns (shared with search_case.py & dashboard.ts).
UI_SELECT_COLUMNS: tuple[str, ...] = (
    "productDisplayName",
    "link",
    "unitPrice",
    "discount",
    "finalPrice",
    "rating",
)

# Limits and numeric bounds.
_INT4_MIN = -2_147_483_648
_INT4_MAX = 2_147_483_647
_MAX_NUMERIC_STR_LEN = 40
_MAX_DECIMAL_EXPONENT = 30
_MAX_STRING_LITERAL_LEN = 500
_MAX_SQL_LENGTH = 8192
_MAX_TOKENS = 1024
_MAX_CONSTRAINT_LEN = 2000
_MAX_CONSTRAINT_DEPTH = 16
_MAX_CONSTRAINT_NODES = 64
_MAX_CONSTRAINT_IN_LIST = 50
_MAX_CONSTRAINT_BINDS = 100
_MAX_PG_INT8 = (1 << 63) - 1
_MAX_ORDER_BY_ITEMS = 8
_MAX_TIMEOUT_MS = 600_000
_MAX_DISPLAY_FORMAT_LEN = 4096
_MAX_DISPLAY_FORMAT_PARENS = 64
_MAX_LIKE_PATTERN_LEN = 128
_MAX_LIKE_WILDCARDS = 6
_MAX_LIKE_PREDICATES = 8

# Precompiled regular expressions.
_IDENTIFIER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]{0,62}\Z", re.ASCII)
_ASCII_NUMERIC_RE = re.compile(
    r"\A[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z",
    re.ASCII,
)
_LEADING_WHERE_RE = re.compile(r"\A\s*WHERE\s+", re.IGNORECASE | re.ASCII)
_PRODUCT_DESC_SUFFIX_RE = re.compile(
    r"here\s+is\s+the\s+product\s+description\s*:?\Z",
    re.IGNORECASE,
)

# Control and non-standard Unicode line-break characters.
# SQL mode allows standard SQL whitespace (\t, \n, \r) while rejecting all other
# C0 (0x00..0x1F), DEL (0x7F), C1 (0x80..0x9F incl. \x85), and U+2028/U+2029.
# Single-line text mode additionally rejects \t, \n, and \r (all C0 controls).
_SQL_FORBIDDEN_CONTROL_CHARS: frozenset[str] = frozenset(
    {chr(code) for code in range(0x20) if code not in (0x09, 0x0A, 0x0D)}
    | {chr(code) for code in range(0x7F, 0xA0)}
    | {"\u2028", "\u2029"}
)
_TEXT_FORBIDDEN_CONTROL_CHARS: frozenset[str] = (
    _SQL_FORBIDDEN_CONTROL_CHARS | {"\t", "\n", "\r"}
)

_COMPARISON_OPS: frozenset[str] = frozenset({"=", "<>", "!=", "<", "<=", ">", ">="})
_EQUALITY_OPS: frozenset[str] = frozenset({"=", "<>", "!="})

# PostgreSQL 17 RESERVED_KEYWORD and TYPE_FUNC_NAME_KEYWORD entries plus DDL/DML words.
_RESERVED_IDENTIFIER_KEYWORDS: frozenset[str] = frozenset({
    "ALL", "ALTER", "ANALYSE", "ANALYZE", "AND", "ANY", "ARRAY", "AS", "ASC",
    "ASYMMETRIC", "AUTHORIZATION", "BETWEEN", "BINARY", "BOTH", "BY", "CALL",
    "CASE", "CAST", "CHECK", "COLLATE", "COLLATION", "COLUMN", "COMMENT",
    "CONCURRENTLY", "CONSTRAINT", "COPY", "CREATE", "CROSS", "CURRENT_CATALOG",
    "CURRENT_DATE", "CURRENT_ROLE", "CURRENT_SCHEMA", "CURRENT_TIME",
    "CURRENT_TIMESTAMP", "CURRENT_USER", "DATABASE", "DEALLOCATE", "DEFAULT",
    "DEFERRABLE", "DELETE", "DESC", "DISCARD", "DISTINCT", "DO", "DROP", "ELSE",
    "END", "EXCEPT", "EXECUTE", "EXISTS", "EXPLAIN", "EXTENSION", "FALSE",
    "FETCH", "FILTER", "FOR", "FOREIGN", "FREEZE", "FROM", "FULL", "GRANT",
    "GROUP", "HAVING", "ILIKE", "IMPORT", "IN", "INDEX", "INITIALLY", "INNER",
    "INSERT", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "LATERAL", "LEADING",
    "LEFT", "LIKE", "LIMIT", "LISTEN", "LOAD", "LOCALTIME", "LOCALTIMESTAMP",
    "LOCK", "MERGE", "NATURAL", "NONE", "NOT", "NOTIFY", "NOTNULL", "NULL",
    "NULLS", "OFFSET", "ON", "ONLY", "OR", "ORDER", "OUTER", "OVER", "OVERLAPS",
    "PLACING", "PREPARE", "PRIMARY", "RECURSIVE", "REFERENCES", "RESET",
    "RETURNING", "REVOKE", "RIGHT", "ROLE", "ROW", "SCHEMA", "SECURITY",
    "SELECT", "SESSION_USER", "SET", "SHOW", "SIMILAR", "SOME", "SYMMETRIC",
    "SYSTEM", "SYSTEM_USER", "TABLE", "TABLESAMPLE", "THEN", "TO", "TRAILING",
    "TRUE", "TRUNCATE", "UNION", "UNIQUE", "UNLISTEN", "UPDATE", "UPSERT",
    "USER", "USING", "VACUUM", "VALUES", "VARIADIC", "VERBOSE", "WHEN", "WHERE",
    "WINDOW", "WITH", "WITHIN",
})

# Standard PostgreSQL dialect for display compilation: named paramstyle avoids
# pg8000's '%(name)s' pyformat rewriting, and _backslash_escapes=False matches
# PostgreSQL's standard_conforming_strings=on behavior.
_DISPLAY_PG_DIALECT = postgresql.dialect(paramstyle="named")
_DISPLAY_PG_DIALECT._backslash_escapes = False

# Hoisted read-only transaction control statements for execute_readonly.
_SQL_SET_TX_READ_ONLY = sa.text("SET TRANSACTION READ ONLY")
_SQL_SET_STATEMENT_TIMEOUT = sa.text(
    "SELECT set_config('statement_timeout', :timeout_ms, true)"
).bindparams(sa.bindparam("timeout_ms", type_=sa.String()))
_SQL_SHOW_TX_READ_ONLY = sa.text("SHOW transaction_read_only")


# ---------------------------------------------------------------------------
# 1. Identifiers, Search Helpers, & Prompt Templates
# ---------------------------------------------------------------------------


def _short_repr(value: Any, *, limit: int = 64) -> str:
    """Returns a bounded repr of an untrusted value for error messages."""
    sample = value[:limit] if isinstance(value, str) and len(value) > limit else value
    rendered = repr(sample)
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[: limit - 3]}..."


def _assert_no_null_or_surrogates(text: str, label: str = "input") -> None:
    """Raises UnsafeSQLError if text contains NUL (U+0000) or UTF-16 surrogates."""
    for ch in text:
        code = ord(ch)
        if code == 0:
            raise UnsafeSQLError(
                f"{label} contains forbidden NUL character U+0000"
            )
        if 0xD800 <= code <= 0xDFFF:
            raise UnsafeSQLError(
                f"{label} contains forbidden UTF-16 surrogate U+{code:04X}"
            )


def _assert_no_forbidden_controls(
    text: str,
    label: str = "SQL input",
    *,
    allow_sql_whitespace: bool = False,
) -> None:
    """Raises UnsafeSQLError if text contains forbidden controls or surrogates."""
    forbidden = (
        _SQL_FORBIDDEN_CONTROL_CHARS
        if allow_sql_whitespace
        else _TEXT_FORBIDDEN_CONTROL_CHARS
    )
    for ch in text:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            raise UnsafeSQLError(
                f"{label} contains forbidden UTF-16 surrogate U+{code:04X}"
            )
        if ch in forbidden:
            raise UnsafeSQLError(
                f"{label} contains forbidden control character U+{code:04X}"
            )


def _is_strict_int(value: Any) -> bool:
    """Returns True only for non-bool Python ints (PEP 8 compliant)."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_sql_identifier(name: Any, label: str = "identifier") -> str:
    """Validates an unquoted ASCII PostgreSQL identifier (<=63 chars, non-system, non-reserved)."""
    if not isinstance(name, str):
        raise UnsafeSQLError(f"{label} must be a non-empty string")
    if _IDENTIFIER_RE.fullmatch(name) is None:
        raise UnsafeSQLError(f"Invalid SQL {label}: {_short_repr(name)}")
    lowered = name.lower()
    if lowered.startswith("pg_") or lowered == "information_schema":
        raise UnsafeSQLError(f"System SQL {label} is not allowed: {_short_repr(name)}")
    if name.upper() in _RESERVED_IDENTIFIER_KEYWORDS:
        raise UnsafeSQLError(
            f"Reserved keyword not allowed as {label}: {_short_repr(name)}"
        )
    return name


def empty_search_result() -> dict[str, Any]:
    """Returns a fresh canonical empty SearchResponse payload."""
    return {"sql_command": "", "details": []}


def clean_search_text(value: Any) -> str:
    """Validates search text; rejects NUL and UTF-16 lone surrogates."""
    if not isinstance(value, str):
        raise UnsafeSQLError("search text must be a string")
    _assert_no_null_or_surrogates(value, label="search text")
    return value


def format_display_sql(stmt: Executable) -> str:
    """Compiles stmt with literal_binds=True for display and formats safely.

    Skips sqlparse when backslashes, length, or paren counts exceed bounds to
    avoid sqlparse backslash-quote desync and recursion/CPU DoS.
    """
    try:
        raw_sql = str(
            stmt.compile(
                dialect=_DISPLAY_PG_DIALECT,
                compile_kwargs={"literal_binds": True},
            )
        )
    except Exception:
        raw_sql = str(stmt)
    if (
        "\\" in raw_sql
        or len(raw_sql) > _MAX_DISPLAY_FORMAT_LEN
        or raw_sql.count("(") > _MAX_DISPLAY_FORMAT_PARENS
    ):
        return raw_sql
    try:
        return sqlparse.format(raw_sql, reindent=True)
    except (RecursionError, Exception):
        return raw_sql


def validate_question_template(raw_template: Any) -> str:
    """Validates and normalizes an ai.if YES/NO question template.

    Rejects NUL and UTF-16 surrogates, strips surrounding whitespace and
    repeated trailing product-description suffixes, and requires a non-empty
    question string.
    """
    if not isinstance(raw_template, str):
        raise UnsafeSQLError("question_template must be a string")
    _assert_no_null_or_surrogates(raw_template, label="question_template")

    cleaned = raw_template.strip()
    while True:
        updated = _PRODUCT_DESC_SUFFIX_RE.sub("", cleaned).strip()
        if updated == cleaned:
            break
        cleaned = updated

    if not cleaned:
        raise UnsafeSQLError("question_template must be non-empty after cleanup")
    return cleaned


def combine_where_clauses(ui_where_sql: str, llm_where_sql: str) -> str:
    """Combines optional UI and LLM WHERE predicates with parentheses against OR bypasses."""
    ui_cond = _LEADING_WHERE_RE.sub("", (ui_where_sql or "").strip()).strip()
    llm_cond = _LEADING_WHERE_RE.sub("", (llm_where_sql or "").strip()).strip()
    if ui_cond and llm_cond:
        return f"WHERE ({ui_cond}) AND ({llm_cond})"
    if ui_cond:
        return f"WHERE ({ui_cond})"
    if llm_cond:
        return f"WHERE ({llm_cond})"
    return ""


# ---------------------------------------------------------------------------
# 2. Catalog Column Literal Coercion
# ---------------------------------------------------------------------------


def _parse_finite_decimal(raw_text: str) -> Decimal:
    """Parses a strictly ASCII finite decimal with bounded length & exponent."""
    if len(raw_text) > _MAX_NUMERIC_STR_LEN:
        raise UnsafeSQLError(
            f"Numeric literal exceeds max length ({_MAX_NUMERIC_STR_LEN})"
        )
    _assert_no_forbidden_controls(raw_text, label="numeric literal")
    cleaned = raw_text.strip(" ")
    if not cleaned or _ASCII_NUMERIC_RE.fullmatch(cleaned) is None:
        raise UnsafeSQLError(f"Invalid numeric literal: {_short_repr(raw_text)}")
    try:
        dec = Decimal(cleaned)
    except InvalidOperation as err:
        raise UnsafeSQLError(
            f"Malformed numeric literal: {_short_repr(raw_text)}"
        ) from err
    if abs(dec.adjusted()) > _MAX_DECIMAL_EXPONENT:
        raise UnsafeSQLError(f"Out-of-range decimal: {_short_repr(raw_text)}")
    return Decimal("0") if dec == 0 else dec


def coerce_column_literal(
    column: str,
    raw_value: Any,
    *,
    is_string_literal: bool = False,
) -> tuple[Any, TypeEngine[Any]]:
    """Coerces a SQL literal string to (typed_value, sa_type) for pg8000 RENDER_CASTS."""
    del is_string_literal
    if not isinstance(column, str):
        raise UnsafeSQLError("column must be a string")
    col_kind = CATALOG_COLUMN_TYPES.get(column.lower())
    if col_kind is None:
        raise UnsafeSQLError(
            f"Unknown or disallowed catalog column: {_short_repr(column)}"
        )
    if not isinstance(raw_value, str):
        raise UnsafeSQLError(f"Unsupported literal value: {_short_repr(raw_value)}")

    if col_kind == "str":
        if len(raw_value) > _MAX_STRING_LITERAL_LEN:
            raise UnsafeSQLError(
                f"String literal exceeds max length ({_MAX_STRING_LITERAL_LEN})"
            )
        _assert_no_forbidden_controls(raw_value, label="string literal")
        return raw_value, sa.String()

    dec = _parse_finite_decimal(raw_value)
    if col_kind == "int" and dec == dec.to_integral_value():
        int_val = int(dec)
        if _INT4_MIN <= int_val <= _INT4_MAX:
            return int_val, sa.Integer()
    return dec, sa.Numeric()


# ---------------------------------------------------------------------------
# 3. Single-Pass PostgreSQL-Aware SQL Tokenizer
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Token:
    """A lexical token emitted by tokenize_sql (kind, normalized value, char pos)."""

    kind: str
    value: str
    pos: int


def _is_ascii_ident_start(ch: str) -> bool:
    return ch.isascii() and (ch.isalpha() or ch == "_")


def _is_ascii_ident_part(ch: str) -> bool:
    return ch.isascii() and (ch.isalnum() or ch == "_")


def _is_ascii_digit(ch: str) -> bool:
    return ch.isascii() and ch.isdigit()


def _scan_single_quoted(sql: str, start: int) -> tuple[str, int]:
    """Scans a standard single-quoted SQL string literal starting at start."""
    length = len(sql)
    idx = start + 1
    chars: list[str] = []
    while idx < length:
        ch = sql[idx]
        if ch == "\\":
            raise UnsafeSQLError(
                f"Backslashes inside string literals are not allowed (pos {idx})"
            )
        if ch == "'":
            if idx + 1 < length and sql[idx + 1] == "'":
                chars.append("'")
                idx += 2
                continue
            return "".join(chars), idx + 1
        chars.append(ch)
        idx += 1
    raise UnsafeSQLError(f"Unterminated string literal starting at pos {start}")


def _scan_double_quoted(sql: str, start: int) -> tuple[str, int]:
    """Scans a double-quoted identifier and validates strict ASCII form."""
    length = len(sql)
    idx = start + 1
    while idx < length:
        ch = sql[idx]
        if ch == '"':
            if idx + 1 < length and sql[idx + 1] == '"':
                raise UnsafeSQLError(
                    f"Escaped quotes in identifiers are not allowed (pos {idx})"
                )
            inner = sql[start + 1 : idx]
            if _IDENTIFIER_RE.fullmatch(inner) is None:
                raise UnsafeSQLError(
                    f"Invalid double-quoted identifier at pos {start}: {_short_repr(inner)}"
                )
            return inner, idx + 1
        idx += 1
    raise UnsafeSQLError(
        f"Unterminated double-quoted identifier starting at pos {start}"
    )


def _scan_number(sql: str, start: int) -> tuple[str, int]:
    """Scans a base-10 numeric literal and rejects hex/underscore/scientific forms."""
    length = len(sql)
    idx = start
    has_dot = sql[idx] == "."
    if has_dot:
        idx += 1
    while idx < length and _is_ascii_digit(sql[idx]):
        idx += 1
    if not has_dot and idx < length and sql[idx] == ".":
        if idx + 1 < length and _is_ascii_digit(sql[idx + 1]):
            idx += 1
            while idx < length and _is_ascii_digit(sql[idx]):
                idx += 1
        else:
            raise UnsafeSQLError(
                f"Malformed decimal literal with trailing dot at pos {start}"
            )
    if idx < length and (_is_ascii_ident_part(sql[idx]) or sql[idx] == "."):
        raise UnsafeSQLError(f"Unsupported numeric literal syntax at pos {start}")
    lexeme = sql[start:idx]
    if len(lexeme) > _MAX_NUMERIC_STR_LEN:
        raise UnsafeSQLError(f"Numeric literal too long at pos {start}")
    return lexeme, idx


_TWO_CHAR_OPS: frozenset[str] = frozenset({"<>", "!=", "<=", ">=", "||"})
_SINGLE_CHAR_PUNCT: Mapping[str, str] = MappingProxyType({
    "(": "LPAREN",
    ")": "RPAREN",
    ",": "COMMA",
    ".": "DOT",
    ";": "SEMI",
    "*": "STAR",
})
_SINGLE_CHAR_OPS: frozenset[str] = frozenset({"=", "<", ">", "+", "-", "/"})


def tokenize_sql(sql: str) -> list[Token]:
    """Tokenizes SQL with PostgreSQL-aware lexical security checks.

    Rejects controls/surrogates, block comments, dollar quotes, prefixed/adjacent
    strings, backslashes in strings, bind placeholders, and non-base-10 numbers;
    strips `--` line comments terminated by CR or LF (matching PG scan.l).
    """
    if not isinstance(sql, str):
        raise UnsafeSQLError("SQL input must be a string")
    if len(sql) > _MAX_SQL_LENGTH:
        raise UnsafeSQLError(f"SQL input exceeds max length ({_MAX_SQL_LENGTH})")
    _assert_no_forbidden_controls(sql, allow_sql_whitespace=True)

    tokens: list[Token] = []
    length = len(sql)
    idx = 0

    def _emit(kind: str, value: str, pos: int) -> None:
        tokens.append(Token(kind=kind, value=value, pos=pos))
        if len(tokens) > _MAX_TOKENS:
            raise UnsafeSQLError("SQL exceeds maximum token limit")

    while idx < length:
        ch = sql[idx]
        if ch in (" ", "\t", "\n", "\r"):
            idx += 1
            continue

        two = sql[idx : idx + 2]

        # Line comments: PostgreSQL scan.l terminates '--' on both '\r' and '\n'.
        if two == "--":
            idx += 2
            while idx < length and sql[idx] not in ("\n", "\r"):
                idx += 1
            continue

        if two in ("/*", "*/"):
            raise UnsafeSQLError(f"Block comments are not allowed (pos {idx})")

        if ch == "$":
            raise UnsafeSQLError(
                f"Dollar quotes and positional params are not allowed (pos {idx})"
            )

        if ch == "'":
            if tokens and tokens[-1].kind == "STRING":
                raise UnsafeSQLError(
                    f"Adjacent string literals are not allowed (pos {idx})"
                )
            value, next_idx = _scan_single_quoted(sql, idx)
            _emit("STRING", value, idx)
            idx = next_idx
            continue

        if ch == '"':
            value, next_idx = _scan_double_quoted(sql, idx)
            _emit("QUOTED_IDENT", value, idx)
            idx = next_idx
            continue

        # Unquoted ASCII identifier (also guards E', B', X', N', U&', U&").
        if _is_ascii_ident_start(ch):
            start = idx
            idx += 1
            while idx < length and _is_ascii_ident_part(sql[idx]):
                idx += 1
            ident = sql[start:idx]
            if idx < length:
                nxt = sql[idx]
                if nxt == "'":
                    raise UnsafeSQLError(
                        f"Prefixed string literal {_short_repr(ident)}' is not allowed (pos {start})"
                    )
                if nxt == "&" and ident.upper() == "U":
                    raise UnsafeSQLError(
                        f"Unicode escape literal/identifier U& is not allowed (pos {start})"
                    )
            if len(ident) > 63:
                raise UnsafeSQLError(
                    f"Identifier exceeds PostgreSQL 63-char limit (pos {start})"
                )
            _emit("IDENT", ident, start)
            continue

        if _is_ascii_digit(ch) or (
            ch == "." and idx + 1 < length and _is_ascii_digit(sql[idx + 1])
        ):
            lexeme, next_idx = _scan_number(sql, idx)
            _emit("NUMBER", lexeme, idx)
            idx = next_idx
            continue

        # Colons: allow '::' typecast only; reject single ':' bind placeholders.
        if ch == ":":
            if two == "::":
                if idx + 2 < length and sql[idx + 2] == ":":
                    raise UnsafeSQLError(f"Invalid colon sequence at pos {idx}")
                _emit("TYPECAST", "::", idx)
                idx += 2
                continue
            raise UnsafeSQLError(
                f"Unquoted bind parameter ':' is not allowed (pos {idx})"
            )

        # Percent: reject Python pyformat tokens %(name)s, %s, %%; allow modulo %.
        if ch == "%":
            if idx + 1 < length and (
                sql[idx + 1] in ("(", "%") or _is_ascii_ident_start(sql[idx + 1])
            ):
                raise UnsafeSQLError(
                    f"Python format token is not allowed (pos {idx})"
                )
            _emit("OP", "%", idx)
            idx += 1
            continue

        if two in _TWO_CHAR_OPS:
            _emit("OP", two, idx)
            idx += 2
            continue

        punct_kind = _SINGLE_CHAR_PUNCT.get(ch)
        if punct_kind is not None:
            _emit(punct_kind, ch, idx)
            idx += 1
            continue

        if ch in _SINGLE_CHAR_OPS:
            _emit("OP", ch, idx)
            idx += 1
            continue

        raise UnsafeSQLError(f"Disallowed character {ch!r} at pos {idx}")

    return tokens


# ---------------------------------------------------------------------------
# 4. Structured sql_constraints Recursive-Descent Compiler
# ---------------------------------------------------------------------------


def _validate_like_pattern(pattern: str, op_kw: str) -> None:
    """Enforces CWE-400 bounds on a LIKE/ILIKE pattern literal."""
    if len(pattern) > _MAX_LIKE_PATTERN_LEN:
        raise UnsafeSQLError(
            f"{op_kw} pattern exceeds max length ({_MAX_LIKE_PATTERN_LEN})"
        )
    wildcard_count = pattern.count("%") + pattern.count("_")
    if wildcard_count > _MAX_LIKE_WILDCARDS:
        raise UnsafeSQLError(
            f"{op_kw} pattern exceeds max wildcard count ({_MAX_LIKE_WILDCARDS})"
        )
    if not pattern.strip("%_"):
        raise UnsafeSQLError(
            f"{op_kw} pattern must contain at least one non-wildcard character"
        )


class _ConstraintParser:
    """Recursive-descent compiler for bounded catalog WHERE predicates."""

    def __init__(
        self,
        tokens: Sequence[Token],
        *,
        param_prefix: str = "llm_c_",
        context_name: str = "sql_constraints",
    ) -> None:
        self._tokens = tokens
        self._pos = 0
        self._node_count = 0
        self._context_name = context_name
        self._param_prefix = param_prefix
        self._binds: dict[str, BindParameter[Any]] = {}
        self._like_count = 0

    def _peek(self, offset: int = 0) -> Token | None:
        idx = self._pos + offset
        return self._tokens[idx] if idx < len(self._tokens) else None

    def _consume(self) -> Token:
        if self._pos >= len(self._tokens):
            raise UnsafeSQLError(f"Unexpected end of {self._context_name}")
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _is_kind(self, kind: str, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok is not None and tok.kind == kind

    def _match_kind(self, kind: str) -> bool:
        if self._is_kind(kind):
            self._pos += 1
            return True
        return False

    def _expect_kind(self, kind: str, desc: str) -> Token:
        tok = self._peek()
        if tok is None or tok.kind != kind:
            got = tok.value if tok else "EOF"
            raise UnsafeSQLError(f"Expected {desc}, got {_short_repr(got)}")
        return self._consume()

    def _is_op(
        self, ops: str | frozenset[str] | tuple[str, ...], offset: int = 0
    ) -> bool:
        tok = self._peek(offset)
        if tok is None or tok.kind != "OP":
            return False
        return tok.value == ops if isinstance(ops, str) else tok.value in ops

    def _is_kw(self, keyword: str, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok is not None and tok.kind == "IDENT" and tok.value.upper() == keyword

    def _match_kw(self, keyword: str) -> bool:
        if self._is_kw(keyword):
            self._pos += 1
            return True
        return False

    def _expect_kw(self, keyword: str) -> None:
        if not self._match_kw(keyword):
            tok = self._peek()
            got = tok.value if tok else "EOF"
            raise UnsafeSQLError(
                f"Expected keyword {keyword}, got {_short_repr(got)}"
            )

    def _bump_nodes(self) -> None:
        self._node_count += 1
        if self._node_count > _MAX_CONSTRAINT_NODES:
            raise UnsafeSQLError(
                f"{self._context_name} exceeds maximum node limit ({_MAX_CONSTRAINT_NODES})"
            )

    def compile(self) -> tuple[str, dict[str, BindParameter[Any]]]:
        """Parses the full token stream into (canonical_sql, bindparams)."""
        sql = self._parse_or(depth=0)
        if self._pos != len(self._tokens):
            tok = self._tokens[self._pos]
            raise UnsafeSQLError(
                f"Unexpected trailing token {_short_repr(tok.value)} at pos {tok.pos}"
            )
        return sql, self._binds

    def _add_bind(self, column: str, raw_val: str) -> str:
        if len(self._binds) >= _MAX_CONSTRAINT_BINDS:
            raise UnsafeSQLError(
                f"{self._context_name} exceeds max bind count ({_MAX_CONSTRAINT_BINDS})"
            )
        typed_val, sa_type = coerce_column_literal(column, raw_val)
        name = f"{self._param_prefix}{len(self._binds)}"
        self._binds[name] = sa.bindparam(name, value=typed_val, type_=sa_type)
        return f":{name}"

    def _parse_or(self, depth: int) -> str:
        parts = [self._parse_and(depth)]
        while self._match_kw("OR"):
            self._bump_nodes()
            parts.append(self._parse_and(depth))
        return " OR ".join(parts)

    def _parse_and(self, depth: int) -> str:
        parts = [self._parse_not(depth)]
        while self._match_kw("AND"):
            self._bump_nodes()
            parts.append(self._parse_not(depth))
        return " AND ".join(parts)

    def _parse_not(self, depth: int) -> str:
        if self._match_kw("NOT"):
            if depth + 1 > _MAX_CONSTRAINT_DEPTH:
                raise UnsafeSQLError(f"{self._context_name} exceeds max nesting depth")
            self._bump_nodes()
            return f"NOT {self._parse_not(depth + 1)}"
        return self._parse_primary(depth)

    def _parse_primary(self, depth: int) -> str:
        if self._peek() is None:
            raise UnsafeSQLError(f"Unexpected end of {self._context_name}")
        if self._match_kind("LPAREN"):
            if depth + 1 > _MAX_CONSTRAINT_DEPTH:
                raise UnsafeSQLError(f"{self._context_name} exceeds max nesting depth")
            self._bump_nodes()
            inner = self._parse_or(depth + 1)
            self._expect_kind("RPAREN", f"closing ')' in {self._context_name}")
            return f"({inner})"
        return self._parse_predicate()

    def _parse_column(self) -> str:
        tok = self._consume()
        if tok.kind not in ("IDENT", "QUOTED_IDENT"):
            raise UnsafeSQLError(
                f"Expected catalog column name at pos {tok.pos}, got {_short_repr(tok.value)}"
            )
        nxt = self._peek()
        if nxt is not None and nxt.kind in ("DOT", "LPAREN", "TYPECAST"):
            raise UnsafeSQLError(
                f"Disallowed token {_short_repr(nxt.value)} after column {_short_repr(tok.value)}"
            )
        canon = tok.value.lower()
        if canon not in CATALOG_COLUMN_TYPES:
            raise UnsafeSQLError(
                f"Unknown or disallowed catalog column: {_short_repr(tok.value)}"
            )
        return canon

    def _parse_lhs(self) -> tuple[str, str]:
        """Parses predicate LHS; returns (emitted_lhs_sql, canonical_column)."""
        column = self._parse_column()
        return column, column

    def _parse_literal(self, column: str) -> str:
        tok = self._peek()
        if tok is None:
            raise UnsafeSQLError(f"Expected literal value in {self._context_name}")
        if tok.kind == "STRING":
            self._consume()
            return self._add_bind(column, tok.value)
        if self._is_op(("+", "-")):
            sign = self._consume().value
            num_tok = self._expect_kind(
                "NUMBER", f"number literal immediately after unary {sign!r}"
            )
            return self._add_bind(column, f"{sign}{num_tok.value}")
        if tok.kind == "NUMBER":
            self._consume()
            return self._add_bind(column, tok.value)
        raise UnsafeSQLError(
            f"Expected literal value at pos {tok.pos}, got {_short_repr(tok.value)}"
        )

    def _parse_predicate(self) -> str:
        self._bump_nodes()
        lhs_sql, column = self._parse_lhs()
        if self._peek() is None:
            raise UnsafeSQLError(f"Incomplete predicate after column {column!r}")

        is_func_lhs = lhs_sql != column

        if self._is_op(_COMPARISON_OPS):
            op = self._consume().value
            if is_func_lhs and op not in _EQUALITY_OPS:
                raise UnsafeSQLError(f"Operator {op!r} is not allowed on {lhs_sql}")
            return f"{lhs_sql} {op} {self._parse_literal(column)}"

        if self._match_kw("IS"):
            if is_func_lhs:
                raise UnsafeSQLError(f"IS NULL is not allowed on {lhs_sql}")
            neg = self._match_kw("NOT")
            self._expect_kw("NULL")
            return f"{lhs_sql} IS {'NOT ' if neg else ''}NULL"

        neg = self._match_kw("NOT")
        if self._match_kw("ILIKE"):
            return self._finish_like(lhs_sql, column, "ILIKE", neg)
        if self._match_kw("LIKE"):
            return self._finish_like(lhs_sql, column, "LIKE", neg)
        if self._match_kw("BETWEEN"):
            if is_func_lhs:
                raise UnsafeSQLError(f"BETWEEN is not allowed on {lhs_sql}")
            low_ref = self._parse_literal(column)
            self._expect_kw("AND")
            high_ref = self._parse_literal(column)
            prefix = "NOT BETWEEN" if neg else "BETWEEN"
            return f"{lhs_sql} {prefix} {low_ref} AND {high_ref}"
        if self._match_kw("IN"):
            return self._finish_in(lhs_sql, column, neg)

        raise UnsafeSQLError(
            f"Disallowed or missing operator after column {column!r}"
        )

    def _finish_like(
        self, lhs_sql: str, column: str, op_kw: str, negated: bool
    ) -> str:
        if CATALOG_COLUMN_TYPES[column] != "str":
            raise UnsafeSQLError(
                f"{op_kw} is only allowed on string columns, not {column!r}"
            )
        self._like_count += 1
        if self._like_count > _MAX_LIKE_PREDICATES:
            raise UnsafeSQLError(
                f"{self._context_name} exceeds max LIKE/ILIKE predicate count ({_MAX_LIKE_PREDICATES})"
            )
        bind_ref = self._parse_literal(column)
        param_name = bind_ref[1:]
        _validate_like_pattern(str(self._binds[param_name].value), op_kw)
        op_str = f"NOT {op_kw}" if negated else op_kw
        return f"{lhs_sql} {op_str} {bind_ref}"

    def _finish_in(self, lhs_sql: str, column: str, negated: bool) -> str:
        self._expect_kind("LPAREN", "'(' after IN")
        if self._is_kind("RPAREN"):
            raise UnsafeSQLError("Empty IN () list is not allowed")

        items: list[str] = []
        while True:
            if len(items) >= _MAX_CONSTRAINT_IN_LIST:
                raise UnsafeSQLError(
                    f"IN list exceeds maximum items ({_MAX_CONSTRAINT_IN_LIST})"
                )
            items.append(self._parse_literal(column))
            if self._match_kind("COMMA"):
                continue
            self._expect_kind("RPAREN", "')' closing IN list")
            break

        op_str = "NOT IN" if negated else "IN"
        return f"{lhs_sql} {op_str} ({', '.join(items)})"


def compile_sql_constraints(
    raw_constraints: Any,
) -> tuple[str, dict[str, BindParameter[Any]]]:
    """Compiles LLM-emitted WHERE constraints into canonical SQL + typed binds.

    Returns ('', {}) for None or empty/'none'/'null' sentinels; fails closed on
    non-string inputs and disallowed tokens/columns/bounds.
    """
    if raw_constraints is None:
        return "", {}
    if not isinstance(raw_constraints, str):
        raise UnsafeSQLError(
            f"sql_constraints must be a string or None, got {type(raw_constraints).__name__}"
        )

    if len(raw_constraints) > _MAX_CONSTRAINT_LEN:
        raise UnsafeSQLError(
            f"sql_constraints exceeds max length ({_MAX_CONSTRAINT_LEN})"
        )

    # Check control chars BEFORE stripping so 'none\x0b' or '\x00' cannot pass.
    _assert_no_forbidden_controls(
        raw_constraints, label="sql_constraints", allow_sql_whitespace=True
    )

    if raw_constraints.strip(" \t\r\n").lower() in ("", "none", "null"):
        return "", {}

    tokens = tokenize_sql(raw_constraints)
    if not tokens:
        raise UnsafeSQLError("Comment-only sql_constraints are not allowed")

    return _ConstraintParser(tokens).compile()


# ---------------------------------------------------------------------------
# 5. Single-Table NL-to-SQL Parser & Token Rebuilder
# ---------------------------------------------------------------------------

_NLA_SELECT_FUNCS: frozenset[str] = frozenset({
    "COUNT", "MIN", "MAX", "AVG", "SUM", "LOWER", "UPPER",
})
_NLA_CASE_FUNCS: frozenset[str] = frozenset({"LOWER", "UPPER"})
_NLA_NUMERIC_AGG_FUNCS: frozenset[str] = frozenset({"AVG", "SUM"})
_UI_SELECT_COLUMNS_LOWER: frozenset[str] = frozenset(
    col.lower() for col in UI_SELECT_COLUMNS
)


@dataclasses.dataclass(frozen=True)
class _ParsedNlaSelect:
    """Validated components of a single-table NL-to-SQL SELECT statement."""

    distinct: bool
    where_sql: str
    order_items: tuple[str, ...]
    limit_val: int | None
    offset_val: int | None
    binds: tuple[BindParameter[Any], ...]


class _NlaSelectParser(_ConstraintParser):
    """Strict single-table SELECT parser/compiler subclassing _ConstraintParser.

    Matches PG17 alias hiding (an explicit FROM alias hides the raw table name)
    and rejects DISTINCT + ORDER BY on non-projected/expression items (42P10).
    """

    def __init__(
        self,
        tokens: Sequence[Token],
        *,
        schema_name: str,
        table_name: str,
    ) -> None:
        super().__init__(tokens, param_prefix="nla_p_", context_name="SQL query")
        self._schema_lower = schema_name.lower()
        self._table_lower = table_name.lower()
        self._allowed_qualifiers: frozenset[str] = frozenset()
        self._select_qualifiers: list[str] = []

    def parse(self) -> _ParsedNlaSelect:
        """Parses and validates a single catalog SELECT statement."""
        self._expect_kw("SELECT")
        distinct = self._match_kw("DISTINCT")
        if distinct and self._is_kw("ON"):
            raise UnsafeSQLError("SELECT DISTINCT ON is not allowed")

        any_agg = self._parse_select_list()
        self._expect_kw("FROM")
        alias = self._parse_from_table()
        self._allowed_qualifiers = frozenset(
            {alias} if alias is not None else {self._table_lower}
        )
        for qual in self._select_qualifiers:
            if qual not in self._allowed_qualifiers:
                raise UnsafeSQLError(
                    f"Unknown table qualifier in SELECT: {_short_repr(qual)}"
                )

        where_sql = self._parse_or(depth=0) if self._match_kw("WHERE") else ""

        order_items: tuple[str, ...] = ()
        if self._match_kw("ORDER"):
            self._expect_kw("BY")
            if any_agg:
                raise UnsafeSQLError(
                    "ORDER BY on ungrouped aggregate SELECT without GROUP BY is not allowed"
                )
            order_items = self._parse_order_by(distinct=distinct)

        limit_val = (
            self._parse_bounded_uint("LIMIT", _MAX_PG_INT8)
            if self._match_kw("LIMIT")
            else None
        )
        offset_val = (
            self._parse_bounded_uint("OFFSET", _MAX_PG_INT8)
            if self._match_kw("OFFSET")
            else None
        )

        self._match_kind("SEMI")
        if self._pos != len(self._tokens):
            tok = self._tokens[self._pos]
            raise UnsafeSQLError(
                f"Unexpected token {_short_repr(tok.value)} at pos {tok.pos}"
            )

        return _ParsedNlaSelect(
            distinct=distinct,
            where_sql=where_sql,
            order_items=order_items,
            limit_val=limit_val,
            offset_val=offset_val,
            binds=tuple(self._binds.values()),
        )

    def _validate_alias(
        self, tok: Token, *, allow_catalog_name: bool = False
    ) -> str:
        if tok.kind != "IDENT":
            raise UnsafeSQLError(
                f"Alias must be an unquoted identifier, got {_short_repr(tok.value)}"
            )
        alias = validate_sql_identifier(tok.value, label="alias")
        if not allow_catalog_name and alias.lower() in CATALOG_COLUMN_TYPES:
            raise UnsafeSQLError(
                f"Alias {_short_repr(alias)} must not shadow a catalog column"
            )
        return alias.lower()

    def _parse_optional_alias(
        self, *, allow_catalog_name: bool = False
    ) -> str | None:
        if self._match_kw("AS"):
            return self._validate_alias(
                self._consume(), allow_catalog_name=allow_catalog_name
            )
        nxt = self._peek()
        if (
            nxt is not None
            and nxt.kind == "IDENT"
            and nxt.value.upper() not in _RESERVED_IDENTIFIER_KEYWORDS
        ):
            return self._validate_alias(
                self._consume(), allow_catalog_name=allow_catalog_name
            )
        return None

    def _parse_qualified_column(self, *, record_qualifier: bool = False) -> str:
        if self._is_kind("DOT", 1):
            qual_tok = self._consume()
            if qual_tok.kind not in ("IDENT", "QUOTED_IDENT"):
                raise UnsafeSQLError(
                    f"Expected table qualifier at pos {qual_tok.pos}, got {_short_repr(qual_tok.value)}"
                )
            qual = qual_tok.value.lower()
            if record_qualifier:
                self._select_qualifiers.append(qual)
            elif qual not in self._allowed_qualifiers:
                raise UnsafeSQLError(
                    f"Unknown table qualifier: {_short_repr(qual_tok.value)}"
                )
            self._consume()  # DOT
        return self._parse_column()

    def _parse_lhs(self) -> tuple[str, str]:
        tok = self._peek()
        if (
            tok is not None
            and tok.kind == "IDENT"
            and tok.value.upper() in _NLA_CASE_FUNCS
            and self._is_kind("LPAREN", 1)
        ):
            func = self._consume().value.upper()
            self._consume()  # LPAREN
            col = self._parse_qualified_column()
            if CATALOG_COLUMN_TYPES[col] != "str":
                raise UnsafeSQLError(
                    f"{func}() is only allowed on string columns, not {col!r}"
                )
            self._expect_kind("RPAREN", f"')' closing {func}()")
            return f"{func}({col})", col
        col = self._parse_qualified_column()
        return col, col

    def _parse_select_list(self) -> bool:
        any_agg = False
        any_unagg = False
        while True:
            self._bump_nodes()
            is_agg = self._parse_select_item()
            any_agg = any_agg or is_agg
            any_unagg = any_unagg or not is_agg
            if not self._match_kind("COMMA"):
                break
        if any_agg and any_unagg:
            raise UnsafeSQLError(
                "Mixing aggregate functions and ungrouped columns without GROUP BY is not allowed"
            )
        return any_agg

    def _parse_select_item(self) -> bool:
        tok = self._peek()
        if tok is None:
            raise UnsafeSQLError("Expected SELECT projection item")
        if self._match_kind("STAR"):
            return False
        if (
            tok.kind in ("IDENT", "QUOTED_IDENT")
            and self._is_kind("DOT", 1)
            and self._is_kind("STAR", 2)
        ):
            self._select_qualifiers.append(self._consume().value.lower())
            self._consume()  # DOT
            self._consume()  # STAR
            return False

        is_agg = False
        if (
            tok.kind == "IDENT"
            and tok.value.upper() in _NLA_SELECT_FUNCS
            and self._is_kind("LPAREN", 1)
        ):
            func = self._consume().value.upper()
            self._consume()  # LPAREN
            is_case = func in _NLA_CASE_FUNCS
            is_agg = not is_case
            if func == "COUNT" and self._match_kind("STAR"):
                pass
            else:
                if not is_case:
                    self._match_kw("DISTINCT")
                col = self._parse_qualified_column(record_qualifier=True)
                if is_case and CATALOG_COLUMN_TYPES[col] != "str":
                    raise UnsafeSQLError(
                        f"{func}() is only allowed on string columns, not {col!r}"
                    )
                if func in _NLA_NUMERIC_AGG_FUNCS and CATALOG_COLUMN_TYPES[col] == "str":
                    raise UnsafeSQLError(
                        f"{func}() requires a numeric column, not {col!r}"
                    )
            self._expect_kind("RPAREN", f"')' closing {func}()")
        else:
            self._parse_qualified_column(record_qualifier=True)

        self._parse_optional_alias(allow_catalog_name=True)
        return is_agg

    def _parse_from_table(self) -> str | None:
        first = self._peek()
        if first is None or first.kind not in ("IDENT", "QUOTED_IDENT"):
            raise UnsafeSQLError(
                "FROM must reference a single catalog table (no subqueries/VALUES)"
            )
        if first.kind == "IDENT" and first.value.upper() in _RESERVED_IDENTIFIER_KEYWORDS:
            raise UnsafeSQLError(f"Disallowed keyword {first.value!r} in FROM clause")
        self._consume()

        if self._match_kind("DOT"):
            second = self._peek()
            if second is None or second.kind not in ("IDENT", "QUOTED_IDENT"):
                raise UnsafeSQLError("Expected table name after schema '.'")
            self._consume()
            if (
                first.value.lower() != self._schema_lower
                or second.value.lower() != self._table_lower
            ):
                raise UnsafeSQLError(
                    f"Access to table {first.value}.{second.value} is not allowed"
                )
        elif first.value.lower() != self._table_lower:
            raise UnsafeSQLError(f"Access to table {first.value!r} is not allowed")

        if self._is_kind("DOT"):
            raise UnsafeSQLError("3-part table names are not allowed")

        alias = self._parse_optional_alias()
        if self._is_kind("LPAREN"):
            raise UnsafeSQLError("Table alias column lists are not allowed")
        if self._is_kind("COMMA"):
            raise UnsafeSQLError("Comma-joins are not allowed")
        return alias

    def _parse_order_by(self, *, distinct: bool) -> tuple[str, ...]:
        items: list[str] = []
        while True:
            if len(items) >= _MAX_ORDER_BY_ITEMS:
                raise UnsafeSQLError(
                    f"ORDER BY exceeds maximum items ({_MAX_ORDER_BY_ITEMS})"
                )
            self._bump_nodes()
            expr_sql, col = self._parse_lhs()
            if distinct and (expr_sql != col or col not in _UI_SELECT_COLUMNS_LOWER):
                raise UnsafeSQLError(
                    f"ORDER BY {expr_sql} is not allowed with SELECT DISTINCT "
                    "(must be a projected UI column)"
                )
            parts = [expr_sql]
            if self._match_kw("ASC"):
                parts.append("ASC")
            elif self._match_kw("DESC"):
                parts.append("DESC")
            if self._match_kw("NULLS"):
                if self._match_kw("FIRST"):
                    parts.extend(("NULLS", "FIRST"))
                elif self._match_kw("LAST"):
                    parts.extend(("NULLS", "LAST"))
                else:
                    raise UnsafeSQLError("Expected FIRST or LAST after NULLS")
            items.append(" ".join(parts))
            if not self._match_kind("COMMA"):
                break
        return tuple(items)

    def _parse_bounded_uint(self, clause_name: str, max_val: int) -> int:
        tok = self._peek()
        if tok is None or tok.kind != "NUMBER" or "." in tok.value:
            raise UnsafeSQLError(
                f"{clause_name} requires a non-negative integer literal"
            )
        self._consume()
        val = int(tok.value)
        if val > max_val:
            raise UnsafeSQLError(
                f"{clause_name} value {val} out of allowed bounds (0..{max_val})"
            )
        return val


def build_safe_nltosql_query(
    raw_sql: str,
    ui_where_sql: str = "",
    ui_params: dict[str, Any] | None = None,
    *,
    table_name: str = "fashion_products",
    schema_name: str = "public",
) -> tuple[TextClause, str]:
    """Validates, parameterizes, and rebuilds an NL-to-SQL SELECT statement.

    Rewrites the outer projection to UI_SELECT_COLUMNS, merges trusted UI
    filters with parentheses, preserves optional bounded typed LIMIT/OFFSET
    binds, and returns (bound_text_clause, formatted_display_sql).
    """
    valid_schema = validate_sql_identifier(schema_name, label="schema_name")
    valid_table = validate_sql_identifier(table_name, label="table_name")
    if not isinstance(ui_where_sql, str):
        raise UnsafeSQLError("ui_where_sql must be a string")
    _assert_no_forbidden_controls(
        ui_where_sql, label="ui_where_sql", allow_sql_whitespace=True
    )

    ui_binds: list[BindParameter[Any]] = []
    if ui_params is not None:
        if not isinstance(ui_params, dict):
            raise UnsafeSQLError("ui_params must be a dict")
        for key, val in ui_params.items():
            if not isinstance(key, str) or _IDENTIFIER_RE.fullmatch(key) is None:
                raise UnsafeSQLError(f"Invalid UI parameter name: {_short_repr(key)}")
            if key.startswith("nla_p_"):
                raise UnsafeSQLError(
                    f"UI param {_short_repr(key)} collides with reserved nla_p_ namespace"
                )
            if isinstance(val, str):
                _assert_no_null_or_surrogates(val, label=f"UI param {key!r}")
            ui_binds.append(sa.bindparam(key, value=val))

    tokens = tokenize_sql(raw_sql)
    if not tokens:
        raise UnsafeSQLError("Empty or comment-only SQL query is not allowed")

    parsed = _NlaSelectParser(
        tokens,
        schema_name=valid_schema,
        table_name=valid_table,
    ).parse()

    parts: list[str] = [
        "SELECT",
        *(("DISTINCT",) if parsed.distinct else ()),
        ", ".join(UI_SELECT_COLUMNS),
        "FROM",
        f"{valid_schema}.{valid_table}",
    ]
    where_clause = combine_where_clauses(ui_where_sql, parsed.where_sql)
    if where_clause:
        parts.append(where_clause)

    if parsed.order_items:
        parts.extend(("ORDER BY", ", ".join(parsed.order_items)))

    nla_binds = list(parsed.binds)
    if parsed.limit_val is not None:
        limit_name = f"nla_p_{len(nla_binds)}"
        nla_binds.append(
            sa.bindparam(limit_name, value=parsed.limit_val, type_=sa.BigInteger())
        )
        parts.extend(("LIMIT", f":{limit_name}"))

    if parsed.offset_val is not None:
        offset_name = f"nla_p_{len(nla_binds)}"
        nla_binds.append(
            sa.bindparam(offset_name, value=parsed.offset_val, type_=sa.BigInteger())
        )
        parts.extend(("OFFSET", f":{offset_name}"))

    try:
        stmt = sa.text(" ".join(parts)).bindparams(*ui_binds, *nla_binds)
    except sa.exc.ArgumentError as err:
        raise UnsafeSQLError(f"UI bind parameter mismatch: {err}") from err
    missing = [name for name, bp in stmt._bindparams.items() if bp.required]
    if missing:
        raise UnsafeSQLError(f"Missing UI parameter value(s): {', '.join(missing)}")
    return stmt, format_display_sql(stmt)


# ---------------------------------------------------------------------------
# 6. Scoped Read-Only Transaction Executor
# ---------------------------------------------------------------------------


def execute_readonly(
    engine: Engine,
    stmt: Executable,
    *,
    timeout_ms: int | None = None,
) -> Sequence[RowMapping]:
    """Executes a pre-bound statement inside a verified PG READ ONLY transaction.

    Optionally applies transaction-local statement_timeout when timeout_ms is
    provided, and verifies SHOW transaction_read_only == 'on' before executing
    stmt so AUTOCOMMIT engines fail closed instead of silently ignoring
    SET TRANSACTION READ ONLY.
    """
    if timeout_ms is not None and (
        not _is_strict_int(timeout_ms) or not (1 <= timeout_ms <= _MAX_TIMEOUT_MS)
    ):
        raise UnsafeSQLError(
            f"timeout_ms must be an int in 1..{_MAX_TIMEOUT_MS}, got {_short_repr(timeout_ms)}"
        )

    with engine.begin() as connection:
        connection.execute(_SQL_SET_TX_READ_ONLY)
        if timeout_ms is not None:
            connection.execute(
                _SQL_SET_STATEMENT_TIMEOUT, {"timeout_ms": str(timeout_ms)}
            )
        ro_state = connection.execute(_SQL_SHOW_TX_READ_ONLY).scalar()
        if not isinstance(ro_state, str) or ro_state.strip().lower() != "on":
            raise UnsafeSQLError(
                "Database connection did not enter READ ONLY transaction mode"
            )
        return connection.execute(stmt).mappings().all()
