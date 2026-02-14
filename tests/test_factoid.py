"""Tests for factoid data model."""

from datetime import datetime

import pytest

from infobot.kb.factoid import Factoid, FactoidType


def test_factoid_creation():
    """Test creating a basic factoid."""
    factoid = Factoid(
        key="python", value="a programming language", factoid_type=FactoidType.IS
    )

    assert factoid.key == "python"
    assert factoid.value == "a programming language"
    assert factoid.factoid_type == FactoidType.IS
    assert factoid.created_at is None
    assert factoid.updated_at is None
    assert factoid.source is None


def test_factoid_key_normalization():
    """Test that factoid keys are normalized to lowercase."""
    factoid = Factoid(key="  PyThOn  ", value="test", factoid_type=FactoidType.IS)

    assert factoid.key == "python"
    assert factoid.value == "test"


def test_factoid_value_stripped():
    """Test that factoid values are stripped."""
    factoid = Factoid(
        key="test", value="  value with spaces  ", factoid_type=FactoidType.IS
    )

    assert factoid.value == "value with spaces"


def test_factoid_type_string_conversion():
    """Test that string type is converted to FactoidType enum."""
    factoid = Factoid(key="test", value="value", factoid_type="is")

    assert factoid.factoid_type == FactoidType.IS
    assert isinstance(factoid.factoid_type, FactoidType)


def test_factoid_empty_key_raises_error():
    """Test that empty key raises ValueError."""
    with pytest.raises(ValueError, match="key cannot be empty"):
        Factoid(key="", value="test", factoid_type=FactoidType.IS)

    with pytest.raises(ValueError, match="key cannot be empty"):
        Factoid(key="   ", value="test", factoid_type=FactoidType.IS)


def test_factoid_empty_value_raises_error():
    """Test that empty value raises ValueError."""
    with pytest.raises(ValueError, match="value cannot be empty"):
        Factoid(key="test", value="", factoid_type=FactoidType.IS)

    with pytest.raises(ValueError, match="value cannot be empty"):
        Factoid(key="test", value="   ", factoid_type=FactoidType.IS)


def test_factoid_with_timestamps():
    """Test factoid with timestamps."""
    now = datetime.utcnow()
    factoid = Factoid(
        key="test",
        value="value",
        factoid_type=FactoidType.IS,
        created_at=now,
        updated_at=now,
        source="testuser",
    )

    assert factoid.created_at == now
    assert factoid.updated_at == now
    assert factoid.source == "testuser"


def test_factoid_has_reply_tag():
    """Test detection of <reply> tag."""
    factoid = Factoid(
        key="test", value="<reply>just the reply", factoid_type=FactoidType.IS
    )

    assert factoid.has_reply_tag
    assert not factoid.has_action_tag
    assert not factoid.has_random_selection


def test_factoid_has_action_tag():
    """Test detection of <action> tag."""
    factoid = Factoid(
        key="test", value="<action>does something", factoid_type=FactoidType.IS
    )

    assert factoid.has_action_tag
    assert not factoid.has_reply_tag
    assert not factoid.has_random_selection


def test_factoid_has_random_selection():
    """Test detection of pipe-separated random selection."""
    factoid = Factoid(
        key="test", value="option1|option2|option3", factoid_type=FactoidType.IS
    )

    assert factoid.has_random_selection
    assert not factoid.has_reply_tag
    assert not factoid.has_action_tag


def test_factoid_reply_tag_overrides_random():
    """Test that <reply> tag overrides random selection detection."""
    factoid = Factoid(
        key="test", value="<reply>has|pipes|in|it", factoid_type=FactoidType.IS
    )

    assert factoid.has_reply_tag
    assert not factoid.has_random_selection


def test_factoid_to_dict():
    """Test converting factoid to dictionary."""
    now = datetime.utcnow()
    factoid = Factoid(
        key="python",
        value="a programming language",
        factoid_type=FactoidType.IS,
        created_at=now,
        updated_at=now,
        source="user123",
    )

    data = factoid.to_dict()

    assert data["key"] == "python"
    assert data["value"] == "a programming language"
    assert data["type"] == "is"
    assert data["created_at"] == now.isoformat()
    assert data["updated_at"] == now.isoformat()
    assert data["source"] == "user123"


def test_factoid_to_dict_without_timestamps():
    """Test converting factoid without timestamps to dictionary."""
    factoid = Factoid(key="test", value="value", factoid_type=FactoidType.IS)

    data = factoid.to_dict()

    assert data["key"] == "test"
    assert data["value"] == "value"
    assert data["type"] == "is"
    assert data["created_at"] is None
    assert data["updated_at"] is None
    assert data["source"] is None


def test_factoid_from_dict():
    """Test creating factoid from dictionary."""
    now = datetime.utcnow()
    data = {
        "key": "python",
        "value": "a programming language",
        "type": "is",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "source": "user123",
    }

    factoid = Factoid.from_dict(data)

    assert factoid.key == "python"
    assert factoid.value == "a programming language"
    assert factoid.factoid_type == FactoidType.IS
    assert factoid.created_at == now
    assert factoid.updated_at == now
    assert factoid.source == "user123"


def test_factoid_from_dict_without_timestamps():
    """Test creating factoid from dictionary without timestamps."""
    data = {
        "key": "test",
        "value": "value",
        "type": "are",
    }

    factoid = Factoid.from_dict(data)

    assert factoid.key == "test"
    assert factoid.value == "value"
    assert factoid.factoid_type == FactoidType.ARE
    assert factoid.created_at is None
    assert factoid.updated_at is None
    assert factoid.source is None


def test_factoid_type_enum_values():
    """Test FactoidType enum values."""
    assert FactoidType.IS.value == "is"
    assert FactoidType.ARE.value == "are"

    # Test string comparison
    assert FactoidType.IS == "is"
    assert FactoidType.ARE == "are"
