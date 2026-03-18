"""
Thread-safe PostgreSQL connection pool backed by ``psycopg`` (v3).

The pool is initialised lazily on first use and derives its DSN from
:pymod:`shared.config`.  All public helpers return connections via a
context manager so that connections are **always** returned to the pool,
even when callers forget to close them.

Usage
-----
>>> from shared.database import get_connection, check_health
>>> with get_connection() as conn:
...     with conn.cursor() as cur:
...         cur.execute("SELECT 1")
...         print(cur.fetchone())
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from os import getenv
from typing import Generator, Optional

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# ── Module-level pool singleton ───────────────────────────────────────────────
_pool: Optional[ConnectionPool] = None


def _get_pool() -> ConnectionPool:
    """Return the module-level pool, creating it on first call."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        logger.info("Initialising connection pool → %s@%s/%s", getenv("DB_USER"), getenv("DB_HOST"), getenv("DB_NAME"))
        CONN_INFO = f"postgresql://{getenv('DB_USER')}:{getenv('DB_PASSWORD')}@{getenv('DB_HOST')}/{getenv('DB_NAME')}"
        _pool = ConnectionPool(
            conninfo=CONN_INFO,
            min_size=2,
            max_size=10,
            # Wait up to 30 s for a connection before raising PoolTimeout
            timeout=30.0,
            kwargs={"autocommit": False, "row_factory": dict_row},
        )
    return _pool


# ── Public API ────────────────────────────────────────────────────────────────


@contextmanager
def get_connection() -> Generator[psycopg.Connection, None, None]:
    """
    Yield a connection from the pool.

    The connection is automatically returned when the ``with`` block exits.
    On unhandled exceptions the transaction is rolled back; on clean exit the
    caller is responsible for calling ``conn.commit()`` if needed.

    Example
    -------
    >>> with get_connection() as conn:
    ...     with conn.cursor() as cur:
    ...         cur.execute("INSERT INTO tickers (symbol) VALUES (%s)", ("AAPL",))
    ...     conn.commit()
    """
    pool = _get_pool()
    with pool.connection() as conn:
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise


def check_health() -> bool:
    """
    Return ``True`` if the database is reachable, ``False`` otherwise.

    Useful for liveness probes and sidebar status indicators.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False


def close_pool() -> None:
    """
    Drain and close the connection pool.

    Call this during graceful shutdown (e.g. SIGTERM handler) to release all
    connections cleanly.
    """
    global _pool  # noqa: PLW0603
    if _pool is not None:
        logger.info("Closing connection pool")
        _pool.close()
        _pool = None


def execute_ddl(sql_path: str) -> None:
    """
    Execute a DDL file (e.g. ``schema.sql``) inside a single transaction.

    Parameters
    ----------
    sql_path : str
        Absolute or relative path to the ``.sql`` file.
    """
    with open(sql_path) as fh:
        ddl = fh.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        logger.info("DDL executed: %s", sql_path)