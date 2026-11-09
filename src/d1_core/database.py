"""Synchronous Flask-facing helpers for Cloudflare D1 on Python Workers.

D1 itself exposes an asynchronous Worker binding. Flask routes are WSGI
(synchronous), so this module uses Pyodide's run_sync bridge, as demonstrated
in Cloudflare's Flask/Workers documentation.

This module intentionally does not create a SQLAlchemy engine and does not
open a network connection. It uses the DB binding attached to the current
Cloudflare Worker request.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from flask import has_request_context, request
from pyodide.ffi import run_sync


class D1ConfigurationError(RuntimeError):
    """Raised when code tries to access D1 outside a configured Worker request."""


class D1QueryError(RuntimeError):
    """Raised when a D1 operation fails or returns an unexpected result."""


def _member(value: Any, name: str, default: Any = None) -> Any:
    """Read a property from either a Python mapping or a JS proxy object."""
    if value is None:
        return default
    try:
        return value[name]
    except (KeyError, TypeError, IndexError, AttributeError):
        pass
    try:
        return getattr(value, name)
    except (AttributeError, TypeError):
        return default


class D1Row:
    """Small mapping/attribute wrapper around a D1 result row."""

    __slots__ = ("_raw",)

    def __init__(self, raw: Any):
        self._raw = raw

    def __getitem__(self, key: str) -> Any:
        marker = object()
        value = _member(self._raw, key, marker)
        if value is marker:
            raise KeyError(key)
        return value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, key: str, default: Any = None) -> Any:
        return _member(self._raw, key, default)

    def as_dict(self, columns: Iterable[str]) -> dict[str, Any]:
        """Return a normal Python dict for a known list of column names."""
        return {column: self.get(column) for column in columns}


class D1Execution:
    """Python-friendly view of a D1 run() result."""

    __slots__ = ("success", "meta", "results")

    def __init__(self, raw: Any):
        self.success = bool(_member(raw, "success", True))
        raw_meta = _member(raw, "meta", None)
        self.meta = D1Row(raw_meta) if raw_meta is not None else D1Row({})
        raw_rows = _member(raw, "results", None)
        if raw_rows is None:
            self.results = []
        else:
            raw_length = _member(raw_rows, "length", None)
            if raw_length is None:
                try:
                    raw_length = len(raw_rows)
                except TypeError:
                    raw_length = 0
            self.results = [D1Row(raw_rows[index]) for index in range(int(raw_length))]

    @property
    def changes(self) -> int:
        return int(self.meta.get("changes", 0) or 0)

    @property
    def last_row_id(self) -> Optional[int]:
        value = self.meta.get("last_row_id")
        return int(value) if value not in (None, 0, "0") else None

    @property
    def rows_read(self) -> int:
        return int(self.meta.get("rows_read", 0) or 0)

    @property
    def rows_written(self) -> int:
        return int(self.meta.get("rows_written", 0) or 0)


class D1Database:
    """Execute prepared SQL statements against the current request's D1 binding.

    Values must always be passed as parameters. SQL identifiers (table and
    column names) cannot be bound; use constants/allowlists for identifiers.
    """

    TABLES = frozenset(
        {
            "admins",
            "contact_enquiries",
            "job_applications",
            "jobs",
            "projects",
            "services",
            "site_settings",
        }
    )

    @staticmethod
    def _binding() -> Any:
        if not has_request_context():
            raise D1ConfigurationError(
                "D1 can only be accessed while handling a Cloudflare Worker request."
            )

        worker_env = request.environ.get("workers.env")
        if worker_env is None:
            raise D1ConfigurationError(
                "Cloudflare Worker environment is missing from the request."
            )

        database = _member(worker_env, "DB")
        if database is None:
            raise D1ConfigurationError(
                "D1 binding 'DB' is missing. Check wrangler.jsonc."
            )
        return database

    def run(self, sql: str, params: Optional[Sequence[Any]] = None) -> D1Execution:
        """Run one prepared statement and return a D1Execution wrapper."""
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("SQL statement must be a non-empty string.")

        values = tuple(params or ())
        statement = self._binding().prepare(sql)
        if values:
            statement = statement.bind(*values)

        try:
            raw_result = run_sync(statement.run())
        except Exception as exc:
            raise D1QueryError(f"D1 query failed: {exc}") from exc

        execution = D1Execution(raw_result)
        if not execution.success:
            raise D1QueryError("D1 reported that the SQL operation was unsuccessful.")
        return execution

    def fetch_all(
        self, sql: str, params: Optional[Sequence[Any]] = None
    ) -> list[D1Row]:
        """Run a SELECT and return all rows."""
        return self.run(sql, params).results

    def fetch_one(
        self, sql: str, params: Optional[Sequence[Any]] = None
    ) -> Optional[D1Row]:
        """Run a SELECT and return its first row, or None."""
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def scalar(
        self,
        sql: str,
        params: Optional[Sequence[Any]] = None,
        default: Any = None,
    ) -> Any:
        """Return the first column of the first row."""
        row = self.fetch_one(sql, params)
        if row is None:
            return default
        # D1 returns column names as keys. For scalar queries in this project,
        # callers should alias the column (for example: AS value).
        return row.get("value", default)

    def table_count(self, table_name: str) -> int:
        """Count rows in one of the known VR Tech Solutions tables."""
        if table_name not in self.TABLES:
            raise ValueError(f"Unsupported table name: {table_name}")
        row = self.fetch_one(
            f'SELECT COUNT(*) AS records FROM "{table_name}"'
        )
        return int(row.get("records", 0) if row else 0)

    def insert(self, sql: str, params: Optional[Sequence[Any]] = None) -> Optional[int]:
        """Execute an INSERT and return D1's last_row_id when supplied."""
        return self.run(sql, params).last_row_id

    def update(self, sql: str, params: Optional[Sequence[Any]] = None) -> int:
        """Execute an UPDATE/DELETE and return the affected-row count."""
        return self.run(sql, params).changes
