"""Database connection management for Infobot Reborn.

Provides async SQLite access with WAL mode enabled.
Suitable for both local development and Modal Volumes.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Manages async SQLite database connections with WAL mode.

    Attributes:
        db_path: Path to the SQLite database file.
        _conn: Active database connection (None when not connected).
        _lock: Asyncio lock for connection management.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize database connection manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish database connection and enable WAL mode.

        Creates parent directories if they don't exist.
        Enables WAL (Write-Ahead Logging) mode for better concurrency.

        Raises:
            aiosqlite.Error: If connection or WAL mode setup fails.
        """
        async with self._lock:
            if self._conn is not None:
                logger.warning("Connection already established")
                return

            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Connect to database
            self._conn = await aiosqlite.connect(str(self.db_path))

            # Enable WAL mode for better concurrency
            await self._conn.execute("PRAGMA journal_mode=WAL")

            # Enable foreign keys
            await self._conn.execute("PRAGMA foreign_keys=ON")

            logger.info(f"Database connected: {self.db_path}")

    async def close(self) -> None:
        """Close database connection if open."""
        async with self._lock:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
                logger.info("Database connection closed")

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[aiosqlite.Cursor]:
        """Get a database cursor within a context manager.

        Yields:
            Database cursor for executing queries.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database connection not established. Call connect() first."
            )

        async with self._conn.cursor() as cur:
            yield cur

    async def execute(
        self, sql: str, parameters: tuple | dict | None = None
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement to execute.
            parameters: Optional parameters for the SQL statement.

        Returns:
            Database cursor with results.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database connection not established. Call connect() first."
            )

        if parameters is None:
            return await self._conn.execute(sql)
        return await self._conn.execute(sql, parameters)

    async def executemany(
        self, sql: str, parameters: list[tuple] | list[dict]
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement with multiple parameter sets.

        Args:
            sql: SQL statement to execute.
            parameters: List of parameter sets.

        Returns:
            Database cursor.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database connection not established. Call connect() first."
            )

        return await self._conn.executemany(sql, parameters)

    async def commit(self) -> None:
        """Commit the current transaction.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database connection not established. Call connect() first."
            )

        await self._conn.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction.

        Raises:
            RuntimeError: If connection is not established.
        """
        if self._conn is None:
            raise RuntimeError(
                "Database connection not established. Call connect() first."
            )

        await self._conn.rollback()

    @property
    def is_connected(self) -> bool:
        """Check if database connection is established."""
        return self._conn is not None
