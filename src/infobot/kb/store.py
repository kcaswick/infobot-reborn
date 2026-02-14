"""Factoid storage and retrieval using SQLite."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from infobot.kb.factoid import Factoid, FactoidType

if TYPE_CHECKING:
    from infobot.db.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class FactoidExistsError(ValueError):
    """Raised when attempting to create a factoid that already exists."""

    pass


class FactoidStore:
    """Manages factoid CRUD operations.

    Provides async interface for creating, reading, updating, and deleting
    factoids in the SQLite database.

    Attributes:
        db: Database connection to use for queries.
    """

    def __init__(self, db: "DatabaseConnection") -> None:
        """Initialize factoid store.

        Args:
            db: Database connection to use.
        """
        self.db = db

    async def create(self, factoid: Factoid) -> Factoid:
        """Create a new factoid.

        Args:
            factoid: Factoid to create.

        Returns:
            Created factoid with timestamps set.

        Raises:
            FactoidExistsError: If factoid with same key and type already exists.
        """
        # Check if factoid already exists
        existing = await self.get(factoid.key, factoid.factoid_type)
        if existing is not None:
            raise FactoidExistsError(
                f"Factoid '{factoid.key}' ({factoid.factoid_type.value}) "
                "already exists"
            )

        # Set timestamps
        now = datetime.utcnow()
        factoid.created_at = now
        factoid.updated_at = now

        # Insert into database
        await self.db.execute(
            """
            INSERT INTO factoids (key, value, type, created_at, updated_at, source)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                factoid.key,
                factoid.value,
                factoid.factoid_type.value,
                factoid.created_at.isoformat(),
                factoid.updated_at.isoformat(),
                factoid.source,
            ),
        )
        await self.db.commit()

        logger.info(f"Created factoid: {factoid.key} ({factoid.factoid_type.value})")
        return factoid

    async def get(
        self, key: str, factoid_type: FactoidType | None = None
    ) -> Factoid | None:
        """Retrieve a factoid by key.

        Args:
            key: Factoid key to look up (case-insensitive).
            factoid_type: Optional type filter. If None, returns first match.

        Returns:
            Factoid if found, None otherwise.
        """
        key = key.strip().lower()

        if factoid_type is not None:
            # Query for specific type
            cursor = await self.db.execute(
                """
                SELECT key, value, type, created_at, updated_at, source
                FROM factoids
                WHERE key = ? AND type = ?
                """,
                (key, factoid_type.value),
            )
        else:
            # Query for any type (prefer 'is' over 'are')
            cursor = await self.db.execute(
                """
                SELECT key, value, type, created_at, updated_at, source
                FROM factoids
                WHERE key = ?
                ORDER BY CASE type WHEN 'is' THEN 0 ELSE 1 END
                LIMIT 1
                """,
                (key,),
            )

        row = await cursor.fetchone()
        if row is None:
            return None

        return Factoid.from_dict(
            {
                "key": row[0],
                "value": row[1],
                "type": row[2],
                "created_at": row[3],
                "updated_at": row[4],
                "source": row[5],
            }
        )

    async def get_all(self, key: str) -> list[Factoid]:
        """Retrieve all factoids for a given key (both 'is' and 'are').

        Args:
            key: Factoid key to look up (case-insensitive).

        Returns:
            List of factoids (may be empty).
        """
        key = key.strip().lower()

        cursor = await self.db.execute(
            """
            SELECT key, value, type, created_at, updated_at, source
            FROM factoids
            WHERE key = ?
            ORDER BY type
            """,
            (key,),
        )

        rows = await cursor.fetchall()
        return [
            Factoid.from_dict(
                {
                    "key": row[0],
                    "value": row[1],
                    "type": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "source": row[5],
                }
            )
            for row in rows
        ]

    async def update(self, factoid: Factoid) -> Factoid:
        """Update an existing factoid.

        Args:
            factoid: Factoid with updated values.

        Returns:
            Updated factoid with new timestamp.

        Raises:
            ValueError: If factoid doesn't exist.
        """
        # Check if factoid exists
        existing = await self.get(factoid.key, factoid.factoid_type)
        if existing is None:
            raise ValueError(
                f"Factoid '{factoid.key}' ({factoid.factoid_type.value}) "
                "does not exist"
            )

        # Update timestamp
        factoid.updated_at = datetime.utcnow()

        # Update in database
        cursor = await self.db.execute(
            """
            UPDATE factoids
            SET value = ?, updated_at = ?, source = ?
            WHERE key = ? AND type = ?
            """,
            (
                factoid.value,
                factoid.updated_at.isoformat(),
                factoid.source,
                factoid.key,
                factoid.factoid_type.value,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"Failed to update factoid '{factoid.key}' "
                f"({factoid.factoid_type.value})"
            )

        await self.db.commit()

        logger.info(f"Updated factoid: {factoid.key} ({factoid.factoid_type.value})")
        return factoid

    async def delete(self, key: str, factoid_type: FactoidType) -> bool:
        """Delete a factoid.

        Args:
            key: Factoid key to delete.
            factoid_type: Type of factoid to delete.

        Returns:
            True if deleted, False if not found.
        """
        key = key.strip().lower()

        cursor = await self.db.execute(
            """
            DELETE FROM factoids
            WHERE key = ? AND type = ?
            """,
            (key, factoid_type.value),
        )

        await self.db.commit()

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted factoid: {key} ({factoid_type.value})")
        else:
            logger.warning(
                f"Factoid not found for deletion: {key} ({factoid_type.value})"
            )

        return deleted

    async def search(self, query: str, limit: int = 10) -> list[Factoid]:
        """Search for factoids by key substring.

        Args:
            query: Search query (case-insensitive substring match).
            limit: Maximum number of results to return.

        Returns:
            List of matching factoids.
        """
        query = query.strip().lower()

        cursor = await self.db.execute(
            """
            SELECT key, value, type, created_at, updated_at, source
            FROM factoids
            WHERE key LIKE ?
            ORDER BY key
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )

        rows = await cursor.fetchall()
        return [
            Factoid.from_dict(
                {
                    "key": row[0],
                    "value": row[1],
                    "type": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "source": row[5],
                }
            )
            for row in rows
        ]

    async def count(self) -> int:
        """Get total number of factoids.

        Returns:
            Total factoid count.
        """
        cursor = await self.db.execute("SELECT COUNT(*) FROM factoids")
        row = await cursor.fetchone()
        return row[0] if row else 0
