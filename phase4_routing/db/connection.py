"""
connection.py — Database connection helper for Phase 4.

Supports two modes controlled by the ``FLOODWATCH_DB_MODE`` env var:

  - ``production`` — Connects to a real PostgreSQL + PostGIS instance
    via psycopg2 using standard PG* env vars.
  - ``mock`` (default) — Uses an in-memory dict store so that all
    Phase 4 code can run locally without a database.
"""

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── Mock connection ─────────────────────────────────────────────────

class MockConnection:
    """
    In-memory mock that mimics a DB connection for local testing.

    Stores flood predictions and road risks in plain Python lists.
    Thread-safe enough for single-process test runs.
    """

    def __init__(self):
        self.flood_predictions: list[dict] = []
        self.road_risks: list[dict] = []
        self._closed = False

    def cursor(self):
        return MockCursor(self)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self._closed = True

    @property
    def closed(self):
        return self._closed


class MockCursor:
    """Minimal cursor mock for the operations used by flood_store.py."""

    def __init__(self, conn: MockConnection):
        self._conn = conn
        self._results: list = []

    def execute(self, query: str, params=None):
        # No-op: actual queries are handled by flood_store's mock path
        pass

    def fetchall(self) -> list:
        return self._results

    def fetchone(self):
        return self._results[0] if self._results else None

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ── Singleton mock connection (re-used across calls) ────────────────

_mock_connection: MockConnection | None = None


def _get_mock_connection() -> MockConnection:
    """Return a shared MockConnection instance."""
    global _mock_connection
    if _mock_connection is None or _mock_connection.closed:
        _mock_connection = MockConnection()
        logger.info("Created new MockConnection (in-memory DB)")
    return _mock_connection


def reset_mock_connection():
    """Reset the mock connection — useful between test runs."""
    global _mock_connection
    _mock_connection = None


# ── Production connection ───────────────────────────────────────────

def _get_production_connection():
    """
    Create a psycopg2 connection to a real PostGIS database.

    Reads from env vars:
        POSTGIS_HOST, POSTGIS_PORT, POSTGIS_DB,
        POSTGIS_USER, POSTGIS_PASS
    """
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get("POSTGIS_HOST", "localhost"),
        port=int(os.environ.get("POSTGIS_PORT", "5432")),
        dbname=os.environ.get("POSTGIS_DB", "floodwatch"),
        user=os.environ.get("POSTGIS_USER", "floodwatch"),
        password=os.environ.get("POSTGIS_PASS", ""),
    )
    logger.info("Connected to PostGIS at %s:%s/%s",
                os.environ.get("POSTGIS_HOST", "localhost"),
                os.environ.get("POSTGIS_PORT", "5432"),
                os.environ.get("POSTGIS_DB", "floodwatch"))
    return conn


# ── Public API ──────────────────────────────────────────────────────

def get_db_mode() -> str:
    """Return the current database mode: 'mock' or 'production'."""
    return os.environ.get("FLOODWATCH_DB_MODE", "mock").lower()


def get_connection():
    """
    Return a database connection for the current mode.

    Returns:
        MockConnection in mock mode, or psycopg2 connection in
        production mode.
    """
    mode = get_db_mode()
    if mode == "production":
        return _get_production_connection()
    return _get_mock_connection()


@contextmanager
def get_managed_connection():
    """
    Context-managed database connection.

    Commits on success, rolls back on exception, and closes the
    connection when done (production mode only — mock connections
    are kept alive for the process lifetime).
    """
    mode = get_db_mode()
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if mode == "production":
            conn.close()
