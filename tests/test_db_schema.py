"""Tests for database schema management."""

import aiosqlite
import pytest

from infobot.db.connection import DatabaseConnection
from infobot.db.schema import SCHEMA_VERSION, initialize_schema, reset_schema


async def test_initialize_schema_creates_tables(
    db_conn_uninitialized: DatabaseConnection,
):
    """Test that initialize_schema creates required tables."""
    await initialize_schema(db_conn_uninitialized)

    # Check schema_version table exists
    cursor = await db_conn_uninitialized.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "schema_version"

    # Check factoids table exists
    cursor = await db_conn_uninitialized.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='factoids'"
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "factoids"


async def test_initialize_schema_sets_version(
    db_conn_uninitialized: DatabaseConnection,
):
    """Test that initialize_schema sets the correct schema version."""
    await initialize_schema(db_conn_uninitialized)

    cursor = await db_conn_uninitialized.execute(
        "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


async def test_initialize_schema_idempotent(db_conn_uninitialized: DatabaseConnection):
    """Test that initialize_schema can be called multiple times."""
    await initialize_schema(db_conn_uninitialized)
    await initialize_schema(db_conn_uninitialized)

    # Should still have only one version entry
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM schema_version")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_factoids_table_structure(db_conn_uninitialized: DatabaseConnection):
    """Test that factoids table has correct structure."""
    await initialize_schema(db_conn_uninitialized)

    # Get table info
    cursor = await db_conn_uninitialized.execute("PRAGMA table_info(factoids)")
    columns = await cursor.fetchall()

    # Extract column names and types
    col_dict = {col[1]: col[2] for col in columns}

    assert "key" in col_dict
    assert col_dict["key"] == "TEXT"

    assert "value" in col_dict
    assert col_dict["value"] == "TEXT"

    assert "type" in col_dict
    assert col_dict["type"] == "TEXT"

    assert "created_at" in col_dict
    assert col_dict["created_at"] == "TEXT"

    assert "updated_at" in col_dict
    assert col_dict["updated_at"] == "TEXT"

    assert "source" in col_dict
    assert col_dict["source"] == "TEXT"


async def test_factoids_table_constraints(db_conn_uninitialized: DatabaseConnection):
    """Test that factoids table enforces type constraint."""
    await initialize_schema(db_conn_uninitialized)

    # Valid types should work
    await db_conn_uninitialized.execute(
        "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
        ("test1", "value1", "is"),
    )
    await db_conn_uninitialized.execute(
        "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
        ("test2", "value2", "are"),
    )
    await db_conn_uninitialized.commit()

    # Invalid type should fail
    with pytest.raises(aiosqlite.IntegrityError):
        await db_conn_uninitialized.execute(
            "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
            ("test3", "value3", "invalid"),
        )
        await db_conn_uninitialized.commit()


async def test_factoids_table_primary_key(db_conn_uninitialized: DatabaseConnection):
    """Test that factoids table enforces primary key (key, type)."""
    await initialize_schema(db_conn_uninitialized)

    # First insert should work
    await db_conn_uninitialized.execute(
        "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
        ("test", "value1", "is"),
    )
    await db_conn_uninitialized.commit()

    # Duplicate (key, type) should fail
    with pytest.raises(aiosqlite.IntegrityError):
        await db_conn_uninitialized.execute(
            "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
            ("test", "value2", "is"),
        )
        await db_conn_uninitialized.commit()

    # But different type should work
    await db_conn_uninitialized.execute(
        "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
        ("test", "value3", "are"),
    )
    await db_conn_uninitialized.commit()


async def test_factoids_index_created(db_conn_uninitialized: DatabaseConnection):
    """Test that index on factoids key is created."""
    await initialize_schema(db_conn_uninitialized)

    cursor = await db_conn_uninitialized.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_factoids_key'"
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "idx_factoids_key"


async def test_reset_schema_drops_and_recreates(
    db_conn_uninitialized: DatabaseConnection,
):
    """Test that reset_schema drops existing data and recreates schema."""
    await initialize_schema(db_conn_uninitialized)

    # Insert some test data
    await db_conn_uninitialized.execute(
        "INSERT INTO factoids (key, value, type) VALUES (?, ?, ?)",
        ("test", "value", "is"),
    )
    await db_conn_uninitialized.commit()

    # Verify data exists
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM factoids")
    row = await cursor.fetchone()
    assert row[0] == 1

    # Reset schema
    await reset_schema(db_conn_uninitialized)

    # Data should be gone
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM factoids")
    row = await cursor.fetchone()
    assert row[0] == 0

    # Schema version should be reset
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM schema_version")
    row = await cursor.fetchone()
    assert row[0] == 1
