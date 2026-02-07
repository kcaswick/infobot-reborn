"""Tests for database connection management."""

from pathlib import Path

import pytest

from infobot.db.connection import DatabaseConnection


@pytest.fixture
async def db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test.db"


async def test_connection_initialization(db_path: Path):
    """Test database connection can be initialized."""
    conn = DatabaseConnection(db_path)
    assert not conn.is_connected
    assert conn.db_path == db_path


async def test_connect_creates_database_file(db_path: Path):
    """Test connect() creates the database file and parent directories."""
    # Use nested path to test parent directory creation
    nested_path = db_path.parent / "nested" / "test.db"
    conn = DatabaseConnection(nested_path)

    assert not nested_path.exists()

    await conn.connect()

    assert nested_path.exists()
    assert conn.is_connected

    await conn.close()


async def test_wal_mode_enabled(db_conn_uninitialized: DatabaseConnection):
    """Test that WAL mode is enabled."""
    cursor = await db_conn_uninitialized.execute("PRAGMA journal_mode")
    row = await cursor.fetchone()
    assert row[0].upper() == "WAL"


async def test_foreign_keys_enabled(db_conn_uninitialized: DatabaseConnection):
    """Test that foreign keys are enabled."""
    cursor = await db_conn_uninitialized.execute("PRAGMA foreign_keys")
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_execute_query(db_conn_uninitialized: DatabaseConnection):
    """Test executing a simple query."""
    cursor = await db_conn_uninitialized.execute("SELECT 1 + 1")
    row = await cursor.fetchone()
    assert row[0] == 2


async def test_execute_with_parameters(db_conn_uninitialized: DatabaseConnection):
    """Test executing query with parameters."""
    # Create a test table
    await db_conn_uninitialized.execute(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, value TEXT)"
    )
    await db_conn_uninitialized.commit()

    # Insert with parameters
    await db_conn_uninitialized.execute(
        "INSERT INTO test_table (id, value) VALUES (?, ?)", (1, "test")
    )
    await db_conn_uninitialized.commit()

    # Query back
    cursor = await db_conn_uninitialized.execute("SELECT value FROM test_table WHERE id = ?", (1,))
    row = await cursor.fetchone()
    assert row[0] == "test"


async def test_executemany(db_conn_uninitialized: DatabaseConnection):
    """Test executing query with multiple parameter sets."""
    await db_conn_uninitialized.execute(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, value TEXT)"
    )
    await db_conn_uninitialized.commit()

    # Insert multiple rows
    await db_conn_uninitialized.executemany(
        "INSERT INTO test_table (id, value) VALUES (?, ?)",
        [(1, "first"), (2, "second"), (3, "third")],
    )
    await db_conn_uninitialized.commit()

    # Verify all rows inserted
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM test_table")
    row = await cursor.fetchone()
    assert row[0] == 3


async def test_commit_and_rollback(db_conn_uninitialized: DatabaseConnection):
    """Test commit and rollback functionality."""
    await db_conn_uninitialized.execute(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, value TEXT)"
    )
    await db_conn_uninitialized.commit()

    # Insert and commit
    await db_conn_uninitialized.execute(
        "INSERT INTO test_table (id, value) VALUES (?, ?)", (1, "committed")
    )
    await db_conn_uninitialized.commit()

    # Insert but rollback
    await db_conn_uninitialized.execute(
        "INSERT INTO test_table (id, value) VALUES (?, ?)", (2, "rolled_back")
    )
    await db_conn_uninitialized.rollback()

    # Check only first row exists
    cursor = await db_conn_uninitialized.execute("SELECT COUNT(*) FROM test_table")
    row = await cursor.fetchone()
    assert row[0] == 1

    cursor = await db_conn_uninitialized.execute("SELECT value FROM test_table WHERE id = 1")
    row = await cursor.fetchone()
    assert row[0] == "committed"


async def test_cursor_context_manager(db_conn_uninitialized: DatabaseConnection):
    """Test using cursor as a context manager."""
    await db_conn_uninitialized.execute(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, value TEXT)"
    )
    await db_conn_uninitialized.execute(
        "INSERT INTO test_table (id, value) VALUES (?, ?)", (1, "test")
    )
    await db_conn_uninitialized.commit()

    async with db_conn_uninitialized.cursor() as cursor:
        await cursor.execute("SELECT value FROM test_table WHERE id = ?", (1,))
        row = await cursor.fetchone()
        assert row[0] == "test"


async def test_execute_without_connection_raises_error(db_path: Path):
    """Test that executing queries without connection raises RuntimeError."""
    conn = DatabaseConnection(db_path)

    with pytest.raises(RuntimeError, match="not established"):
        await conn.execute("SELECT 1")


async def test_cursor_without_connection_raises_error(db_path: Path):
    """Test that getting cursor without connection raises RuntimeError."""
    conn = DatabaseConnection(db_path)

    with pytest.raises(RuntimeError, match="not established"):
        async with conn.cursor():
            pass


async def test_close_idempotent(db_conn_uninitialized: DatabaseConnection):
    """Test that close() can be called multiple times safely."""
    await db_conn_uninitialized.close()
    assert not db_conn_uninitialized.is_connected

    # Should not raise error
    await db_conn_uninitialized.close()
    assert not db_conn_uninitialized.is_connected


async def test_connect_idempotent(db_conn_uninitialized: DatabaseConnection):
    """Test that connect() can be called multiple times safely."""
    assert db_conn_uninitialized.is_connected

    # Should not raise error (just log warning)
    await db_conn_uninitialized.connect()
    assert db_conn_uninitialized.is_connected
