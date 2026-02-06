"""Tests for factoid storage."""

from pathlib import Path

import pytest

from infobot.db.connection import DatabaseConnection
from infobot.db.schema import initialize_schema
from infobot.kb.factoid import Factoid, FactoidType
from infobot.kb.store import FactoidStore


@pytest.fixture
async def db_conn(tmp_path: Path) -> DatabaseConnection:
    """Provide a connected database with schema initialized."""
    conn = DatabaseConnection(tmp_path / "test.db")
    await conn.connect()
    await initialize_schema(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def store(db_conn: DatabaseConnection) -> FactoidStore:
    """Provide a factoid store."""
    return FactoidStore(db_conn)


async def test_create_factoid(store: FactoidStore):
    """Test creating a factoid."""
    factoid = Factoid(
        key="python", value="a programming language", factoid_type=FactoidType.IS
    )

    created = await store.create(factoid)

    assert created.key == "python"
    assert created.value == "a programming language"
    assert created.factoid_type == FactoidType.IS
    assert created.created_at is not None
    assert created.updated_at is not None
    assert created.created_at == created.updated_at


async def test_create_duplicate_raises_error(store: FactoidStore):
    """Test that creating duplicate factoid raises ValueError."""
    factoid = Factoid(key="test", value="value1", factoid_type=FactoidType.IS)

    await store.create(factoid)

    # Try to create duplicate
    duplicate = Factoid(key="test", value="value2", factoid_type=FactoidType.IS)

    with pytest.raises(ValueError, match="already exists"):
        await store.create(duplicate)


async def test_create_same_key_different_type(store: FactoidStore):
    """Test creating factoids with same key but different types."""
    factoid_is = Factoid(key="test", value="value1", factoid_type=FactoidType.IS)
    factoid_are = Factoid(key="test", value="value2", factoid_type=FactoidType.ARE)

    await store.create(factoid_is)
    await store.create(factoid_are)

    # Both should exist
    retrieved_is = await store.get("test", FactoidType.IS)
    retrieved_are = await store.get("test", FactoidType.ARE)

    assert retrieved_is is not None
    assert retrieved_is.value == "value1"
    assert retrieved_are is not None
    assert retrieved_are.value == "value2"


async def test_get_factoid(store: FactoidStore):
    """Test retrieving a factoid."""
    factoid = Factoid(key="python", value="a language", factoid_type=FactoidType.IS)
    await store.create(factoid)

    retrieved = await store.get("python", FactoidType.IS)

    assert retrieved is not None
    assert retrieved.key == "python"
    assert retrieved.value == "a language"
    assert retrieved.factoid_type == FactoidType.IS


async def test_get_factoid_case_insensitive(store: FactoidStore):
    """Test that get is case-insensitive."""
    factoid = Factoid(key="python", value="a language", factoid_type=FactoidType.IS)
    await store.create(factoid)

    # Try different cases
    assert await store.get("PYTHON", FactoidType.IS) is not None
    assert await store.get("Python", FactoidType.IS) is not None
    assert await store.get("pYtHoN", FactoidType.IS) is not None


async def test_get_factoid_not_found(store: FactoidStore):
    """Test retrieving non-existent factoid returns None."""
    retrieved = await store.get("nonexistent", FactoidType.IS)
    assert retrieved is None


async def test_get_factoid_without_type(store: FactoidStore):
    """Test getting factoid without specifying type prefers 'is'."""
    await store.create(
        Factoid(key="test", value="is value", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="test", value="are value", factoid_type=FactoidType.ARE)
    )

    # Get without type should prefer 'is'
    retrieved = await store.get("test")

    assert retrieved is not None
    assert retrieved.value == "is value"
    assert retrieved.factoid_type == FactoidType.IS


async def test_get_all_factoids(store: FactoidStore):
    """Test retrieving all factoids for a key."""
    await store.create(
        Factoid(key="test", value="is value", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="test", value="are value", factoid_type=FactoidType.ARE)
    )

    factoids = await store.get_all("test")

    assert len(factoids) == 2
    assert any(f.factoid_type == FactoidType.ARE for f in factoids)
    assert any(f.factoid_type == FactoidType.IS for f in factoids)


async def test_update_factoid(store: FactoidStore):
    """Test updating a factoid."""
    factoid = Factoid(key="test", value="old value", factoid_type=FactoidType.IS)
    created = await store.create(factoid)

    # Update the value
    created.value = "new value"
    created.source = "updater"

    updated = await store.update(created)

    assert updated.value == "new value"
    assert updated.source == "updater"
    assert updated.updated_at > updated.created_at

    # Verify in database
    retrieved = await store.get("test", FactoidType.IS)
    assert retrieved is not None
    assert retrieved.value == "new value"


async def test_update_nonexistent_raises_error(store: FactoidStore):
    """Test updating non-existent factoid raises ValueError."""
    factoid = Factoid(key="nonexistent", value="value", factoid_type=FactoidType.IS)

    with pytest.raises(ValueError, match="does not exist"):
        await store.update(factoid)


async def test_delete_factoid(store: FactoidStore):
    """Test deleting a factoid."""
    factoid = Factoid(key="test", value="value", factoid_type=FactoidType.IS)
    await store.create(factoid)

    # Delete it
    deleted = await store.delete("test", FactoidType.IS)

    assert deleted is True

    # Verify it's gone
    retrieved = await store.get("test", FactoidType.IS)
    assert retrieved is None


async def test_delete_nonexistent_returns_false(store: FactoidStore):
    """Test deleting non-existent factoid returns False."""
    deleted = await store.delete("nonexistent", FactoidType.IS)
    assert deleted is False


async def test_delete_one_type_keeps_other(store: FactoidStore):
    """Test deleting one type keeps the other."""
    await store.create(
        Factoid(key="test", value="is value", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="test", value="are value", factoid_type=FactoidType.ARE)
    )

    # Delete 'is' type
    await store.delete("test", FactoidType.IS)

    # 'are' should still exist
    retrieved = await store.get("test", FactoidType.ARE)
    assert retrieved is not None
    assert retrieved.value == "are value"


async def test_search_factoids(store: FactoidStore):
    """Test searching for factoids."""
    await store.create(
        Factoid(key="python", value="a language", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="ruby", value="another language", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="javascript", value="web language", factoid_type=FactoidType.IS)
    )

    # Search for "py"
    results = await store.search("py")

    assert len(results) == 1
    assert results[0].key == "python"


async def test_search_case_insensitive(store: FactoidStore):
    """Test that search is case-insensitive."""
    await store.create(
        Factoid(key="python", value="a language", factoid_type=FactoidType.IS)
    )

    results = await store.search("PY")

    assert len(results) == 1
    assert results[0].key == "python"


async def test_search_with_limit(store: FactoidStore):
    """Test search respects limit parameter."""
    for i in range(20):
        await store.create(
            Factoid(key=f"test{i:02d}", value="value", factoid_type=FactoidType.IS)
        )

    results = await store.search("test", limit=5)

    assert len(results) == 5


async def test_count_factoids(store: FactoidStore):
    """Test counting factoids."""
    assert await store.count() == 0

    await store.create(
        Factoid(key="test1", value="value1", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="test2", value="value2", factoid_type=FactoidType.IS)
    )
    await store.create(
        Factoid(key="test1", value="value3", factoid_type=FactoidType.ARE)
    )

    assert await store.count() == 3


async def test_factoid_with_special_formatting(store: FactoidStore):
    """Test storing factoids with special formatting."""
    factoids = [
        Factoid(key="test1", value="<reply>just this", factoid_type=FactoidType.IS),
        Factoid(
            key="test2", value="<action>does something", factoid_type=FactoidType.IS
        ),
        Factoid(key="test3", value="opt1|opt2|opt3", factoid_type=FactoidType.IS),
        Factoid(key="test4", value="hello $who", factoid_type=FactoidType.IS),
    ]

    for factoid in factoids:
        await store.create(factoid)

    # Verify all were stored correctly
    for factoid in factoids:
        retrieved = await store.get(factoid.key)
        assert retrieved is not None
        assert retrieved.value == factoid.value
