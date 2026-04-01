"""Database schema management for Infobot Reborn.

Handles schema creation and migration for factoids and related tables.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infobot.db.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Current schema version
SCHEMA_VERSION = 1

# SQL for creating the factoids table
CREATE_FACTOIDS_TABLE = """
CREATE TABLE IF NOT EXISTS factoids (
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('is', 'are')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT,
    PRIMARY KEY (key, type)
)
"""

# Index for faster lookups
CREATE_FACTOIDS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_factoids_key ON factoids(key)
"""

# SQL for schema version tracking
CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


async def initialize_schema(db: "DatabaseConnection") -> None:
    """Initialize database schema.

    Creates all required tables and indexes if they don't exist.
    Sets up schema version tracking.

    Args:
        db: Database connection to use.

    Raises:
        aiosqlite.Error: If schema creation fails.
    """
    logger.info("Initializing database schema")

    # Create schema version table
    await db.execute(CREATE_SCHEMA_VERSION_TABLE)
    await db.commit()

    # Check current schema version
    cursor = await db.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    current_version = row[0] if row else 0

    if current_version >= SCHEMA_VERSION:
        logger.info(f"Schema already at version {current_version}")
        return

    # Apply migrations
    if current_version < 1:
        await _apply_migration_v1(db)
        await db.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
        await db.commit()
        logger.info("Applied migration to version 1")

    logger.info(f"Schema initialization complete (version {SCHEMA_VERSION})")


async def _apply_migration_v1(db: "DatabaseConnection") -> None:
    """Apply schema version 1: create factoids table.

    Args:
        db: Database connection to use.
    """
    # Create factoids table
    await db.execute(CREATE_FACTOIDS_TABLE)

    # Create indexes
    await db.execute(CREATE_FACTOIDS_INDEX)

    logger.info("Created factoids table and indexes")


async def reset_schema(db: "DatabaseConnection") -> None:
    """Drop all tables and reinitialize schema.

    WARNING: This deletes all data in the database.

    Args:
        db: Database connection to use.
    """
    logger.warning("Resetting database schema - all data will be lost")

    # Drop tables in reverse dependency order
    await db.execute("DROP TABLE IF EXISTS factoids")
    await db.execute("DROP TABLE IF EXISTS schema_version")
    await db.commit()

    # Reinitialize
    await initialize_schema(db)

    logger.info("Schema reset complete")
