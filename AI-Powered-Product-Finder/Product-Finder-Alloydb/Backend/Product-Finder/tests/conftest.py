"""Pytest harness for ephemeral local PostgreSQL 17 + FastAPI TestClient.

Spins up a session-scoped PostgreSQL 17 instance strictly on 127.0.0.1 with
pgvector, AlloyDB AI SQL stubs, catalog seed rows, and security canary objects.
"""

from __future__ import annotations

import atexit
from collections.abc import Callable, Iterator
from decimal import Decimal
import glob
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import ModuleType
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
import sqlalchemy
from sqlalchemy import text
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

CANARY_SECRET = "TEST_CANARY_SECRET_TOKEN"

os.environ.update({
    "INSTANCE_URI": "projects/test-proj/locations/us-central1/clusters/c/instances/i",
    "DB_USER": "postgres", "DB_PASSWORD": "", "DB_NAME": "postgres",
    "ALLOYDB_SCHEMA_NAME": "alloydb_usecase", "TABLE_NAME": "fashion_products",
    "EMBEDDING": "text-embedding-005", "NLA_API": "https://example.invalid/nla",
    "NLA_SERVICE_ACCOUNT": "/dev/null", "CLUSTER_ID": "test-cluster", "INSTANCE_ID": "test-instance",
    "VECTOR_THRESHOLD": "0.5", "HYBRID_THRESHOLD": "0.4", "RATING_THRESHOLD": "5.0",
    "CONTEXT_SET_ID": "test-context", "PROJECT_ID": "test-project", "LOCATION": "us-central1",
    "SCOPES": "https://www.googleapis.com/auth/cloud-platform",
})

_SEED_PRODUCTS_SQL = """
INSERT INTO alloydb_usecase.fashion_products (
    id, gender, masterCategory, subCategory, articleType, baseColour, season, year, usage,
    productDisplayName, brand, link, unitPrice, discount, finalPrice, rating, stockCode, stockStatus
) VALUES
    (1, 'Men', 'Footwear', 'Shoes', 'Sports Shoes', 'Black', 'Summer', 2012, 'Sports', 'Nike Men Black Running Shoes', 'Nike', 'https://example.com/images/nike-1.jpg', 100.00, 40, 60.00, 4.5, 'SKU001', 'In Stock'),
    (2, 'Women', 'Footwear', 'Shoes', 'Casual Shoes', 'Red', 'Winter', 2015, 'Casual', 'Nike Women Red Casual Shoes', 'Nike', 'https://example.com/images/nike-2.jpg', 20.00, 50, 10.00, 4.2, 'SKU002', 'In Stock'),
    (3, 'Women', 'Apparel', 'Topwear', 'Kurtas', 'Blue', 'Summer', 2020, 'Ethnic', 'Biba Women Blue Cotton Kurta', 'Biba', 'https://example.com/images/biba-3.jpg', 50.00, 20, 40.00, 4.8, 'SKU003', 'In Stock'),
    (4, 'Men', 'Accessories', 'Belts', 'Belts', 'Brown', 'Fall', 2018, 'Casual', 'Levis Men Brown Leather Belt', 'Levis', 'https://example.com/images/levis-4.jpg', 25.00, 10, 22.50, 3.9, 'SKU004', 'In Stock'),
    (5, 'Men', 'Apparel', 'Topwear', 'Shirts', 'White', 'Spring', 2012, 'Formal', 'Puma Men White Cotton Shirt', 'Puma', 'https://example.com/images/puma-5.jpg', 30.00, 50, 15.00, 4.0, '123ABC', 'In Stock')
ON CONFLICT (id) DO NOTHING
"""

_UPDATE_DESC_SQL = """
UPDATE alloydb_usecase.fashion_products SET combined_description = CONCAT(
    'Product ID is ', id, ', Product targeted to ', gender, ', Primary or master category is ', masterCategory,
    ', Secondary or sub-category is ', subCategory, ', Type of product is ', articleType,
    ', Descriptive color name or Base colour is ', baseColour, ', Fashion season this product is targeted to is ', season,
    ', Fashion year this product is from is ', year, ', This product meant to be used as  OR usage type is ', usage,
    ', Product name including the brand as the first word is ', productDisplayName, ', Brand name is ', brand,
    ', Unit price is ', unitPrice, ', Discount applied is ', discount, ', Final price or the actual price of the product is ', finalPrice,
    ', Customer rating is ', rating, ', Stock code or stock id is ', stockCode, ', and Stock status is ', stockStatus, '.'
)
"""

_UPDATE_EMBED_SQL = (
    "UPDATE alloydb_usecase.fashion_products "
    "SET combined_description_embedding = google_ml.embedding('text-embedding-005', combined_description) "
    "WHERE combined_description IS NOT NULL"
)

SEED_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS alloydb_usecase;
CREATE SCHEMA IF NOT EXISTS google_ml;
CREATE SCHEMA IF NOT EXISTS ai;

CREATE OR REPLACE FUNCTION google_ml.embedding(model_id text, content text)
RETURNS real[] LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
    SELECT array_fill(0.1::real, ARRAY[768]);
$$;

CREATE OR REPLACE FUNCTION ai.if(
    prompts text[], batch_size integer DEFAULT NULL, model_id varchar(100) DEFAULT NULL
) RETURNS boolean[] LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE WHEN prompts IS NULL THEN NULL::boolean[]
        ELSE COALESCE((SELECT array_agg(TRUE ORDER BY ord) FROM unnest(prompts) WITH ORDINALITY AS t(p, ord)), ARRAY[]::boolean[])
    END;
$$;

CREATE OR REPLACE FUNCTION ai.generate(prompt text, model_id varchar(100) DEFAULT NULL)
RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT '{{"selected_strategy":"vector","reasoning":"stubbed local response","parameters":{{"semantic_text":"shoes","sql_constraints":"None","raw_query":"stub"}},"decision_path":["gate:passed","strategy:vector","ai.if:not_applicable"]}}'::text;
$$;

CREATE TABLE IF NOT EXISTS alloydb_usecase.fashion_products (
    id INT PRIMARY KEY, gender TEXT, masterCategory TEXT, subCategory TEXT, articleType TEXT,
    baseColour TEXT, season TEXT, year INT, usage TEXT, productDisplayName TEXT, brand TEXT,
    link TEXT, unitPrice NUMERIC(10,2), discount INT, finalPrice NUMERIC(10,2),
    rating NUMERIC(3,1), stockCode VARCHAR(20), stockStatus TEXT
);
ALTER TABLE alloydb_usecase.fashion_products
    ADD COLUMN IF NOT EXISTS combined_description TEXT,
    ADD COLUMN IF NOT EXISTS combined_description_embedding VECTOR(768);
{_SEED_PRODUCTS_SQL};
{_UPDATE_DESC_SQL};
{_UPDATE_EMBED_SQL};
CREATE INDEX IF NOT EXISTS fashion_products_combined_description_gin_idx
    ON alloydb_usecase.fashion_products USING gin(to_tsvector('english', combined_description));

CREATE TABLE IF NOT EXISTS public.security_canary (secret TEXT NOT NULL);
DELETE FROM public.security_canary;
INSERT INTO public.security_canary (secret) VALUES ('{CANARY_SECRET}');
CREATE SEQUENCE IF NOT EXISTS public.security_canary_seq START 1;
"""

_RESET_STATEMENTS = (
    "DELETE FROM alloydb_usecase.fashion_products",
    _SEED_PRODUCTS_SQL,
    _UPDATE_DESC_SQL,
    _UPDATE_EMBED_SQL,
    "DELETE FROM public.security_canary",
    f"INSERT INTO public.security_canary (secret) VALUES ('{CANARY_SECRET}')",
    "ALTER SEQUENCE public.security_canary_seq RESTART WITH 1",
)

_REQUIRED_PG_TOOLS = ("initdb", "pg_ctl", "postgres", "psql")
_STANDARD_PG_BIN_GLOBS = (
    "/usr/lib/postgresql/*/bin",
    "/usr/pgsql-*/bin",
    "/opt/homebrew/opt/postgresql*/bin",
    "/usr/local/opt/postgresql*/bin",
)


def _find_free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_pg_cmd(cmd: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"PG command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return proc


def _has_pg_tools(directory: Path) -> bool:
    return all((directory / tool).is_file() for tool in _REQUIRED_PG_TOOLS)


def _resolve_pg_bin() -> Path | None:
    explicit_dir = os.environ.get("PG_BIN_DIR") or os.environ.get("PG17_BIN")
    if explicit_dir:
        pg_bin = Path(explicit_dir).expanduser()
        if not _has_pg_tools(pg_bin):
            missing = [t for t in _REQUIRED_PG_TOOLS if not (pg_bin / t).is_file()]
            raise RuntimeError(f"PostgreSQL binaries missing in {pg_bin}: {', '.join(missing)}")
        return pg_bin

    candidates: list[Path] = []
    if initdb_on_path := shutil.which("initdb"):
        candidates.append(Path(initdb_on_path).resolve().parent)
    for pattern in _STANDARD_PG_BIN_GLOBS:
        candidates.extend(Path(m) for m in sorted(glob.glob(pattern), reverse=True))
    for candidate in candidates:
        if _has_pg_tools(candidate):
            return candidate
    return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _terminate_postmaster_pid(pidfile: Path) -> None:
    """Escalate SIGTERM -> SIGKILL for a lingering postmaster recorded in pidfile."""
    if not pidfile.is_file():
        return
    try:
        pid = int(pidfile.read_text(encoding="utf-8").splitlines()[0].strip())
    except (OSError, IndexError, ValueError):
        return
    if pid <= 1 or not _pid_is_alive(pid):
        return
    for sig, wait_secs in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + wait_secs
        while time.monotonic() < deadline:
            if not _pid_is_alive(pid):
                return
            time.sleep(0.05)


@pytest.fixture(scope="session")
def pg17_cluster() -> Iterator[dict[str, object]]:
    pg_bin = _resolve_pg_bin()
    if pg_bin is None:
        pytest.skip("Local PostgreSQL 17 with pgvector not found (set PG_BIN_DIR)")
    tmpdir = Path(tempfile.mkdtemp(prefix="pg17_product_finder_"))
    pgdata, sockdir = tmpdir / "pgdata", tmpdir / "sock"
    logfile, seed_file, pidfile = tmpdir / "postgres.log", tmpdir / "seed.sql", pgdata / "postmaster.pid"
    sockdir.mkdir(mode=0o700)
    seed_file.write_text(SEED_SQL, encoding="utf-8")
    state = {"started": False, "cleaned": False}

    def _cleanup() -> None:
        if state["cleaned"]:
            return
        state["cleaned"] = True
        if state["started"] or pidfile.exists():
            stop_failed = False
            try:
                stop_proc = subprocess.run(
                    [str(pg_bin / "pg_ctl"), "-D", str(pgdata), "-m", "fast", "stop"],
                    capture_output=True, text=True, check=False, timeout=15.0,
                )
                stop_failed = stop_proc.returncode != 0
            except subprocess.TimeoutExpired:
                stop_failed = True
            if stop_failed or pidfile.exists():
                _terminate_postmaster_pid(pidfile)
        if tmpdir.exists():
            shutil.rmtree(tmpdir, ignore_errors=True)

    atexit.register(_cleanup)
    try:
        _run_pg_cmd([str(pg_bin / "initdb"), "-D", str(pgdata), "-U", "postgres", "-A", "trust", "--no-locale", "--encoding=UTF8"])
        port = _find_free_loopback_port()
        escaped_sockdir = str(sockdir).replace("'", "''")
        with (pgdata / "postgresql.conf").open("a", encoding="utf-8") as conf:
            conf.write(
                f"\nlisten_addresses = '127.0.0.1'\nport = {port}\nunix_socket_directories = '{escaped_sockdir}'\n"
                "fsync = off\nsynchronous_commit = off\nfull_page_writes = off\n"
            )
        _run_pg_cmd([str(pg_bin / "pg_ctl"), "-D", str(pgdata), "-l", str(logfile), "-w", "-t", "30", "start"], timeout=45.0)
        state["started"] = True
        psql_base = [str(pg_bin / "psql"), "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", "postgres"]
        listen_addr = _run_pg_cmd([*psql_base, "-tAc", "SHOW listen_addresses;"], timeout=30.0).stdout.strip()
        assert listen_addr == "127.0.0.1", f"Expected loopback only, got {listen_addr}"
        _run_pg_cmd([*psql_base, "-v", "ON_ERROR_STOP=1", "-f", str(seed_file)])
        yield {"port": port, "db_url": f"postgresql+pg8000://postgres@127.0.0.1:{port}/postgres", "pgdata": pgdata, "tmpdir": tmpdir, "pg_bin": pg_bin}
    finally:
        _cleanup()
        atexit.unregister(_cleanup)


@pytest.fixture(scope="session")
def pg_engine(pg17_cluster: dict[str, object]) -> Iterator[Engine]:
    engine = sqlalchemy.create_engine(str(pg17_cluster["db_url"]))
    engine.dialect.description_encoding = None
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def app_module(pg_engine: Engine) -> ModuleType:
    with (
        patch("google.cloud.alloydbconnector.Connector"),
        patch("db.alloydb_client.AlloyDBClient.create_engine", return_value=pg_engine),
    ):
        import app as product_finder_app
    product_finder_app.engine = pg_engine
    return product_finder_app


@pytest.fixture()
def reset_db(pg_engine: Engine) -> None:
    with pg_engine.begin() as conn:
        for stmt in _RESET_STATEMENTS:
            conn.execute(text(stmt))


@pytest.fixture()
def client(app_module: ModuleType, reset_db: None) -> Iterator[TestClient]:
    del reset_db
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def canary_secret() -> str:
    return CANARY_SECRET


@pytest.fixture()
def seq_last_value(pg_engine: Engine) -> Callable[[], int | None]:
    def _read() -> int | None:
        with pg_engine.connect() as conn:
            return conn.execute(
                text("SELECT last_value FROM pg_sequences WHERE schemaname = 'public' AND sequencename = 'security_canary_seq'")
            ).scalar()
    return _read


@pytest.fixture()
def product_final_price(pg_engine: Engine) -> Callable[[int], Decimal]:
    def _read(product_id: int) -> Decimal:
        with pg_engine.connect() as conn:
            val = conn.execute(
                text("SELECT finalPrice FROM alloydb_usecase.fashion_products WHERE id = :pid"), {"pid": product_id},
            ).scalar_one()
            return Decimal(str(val))
    return _read
