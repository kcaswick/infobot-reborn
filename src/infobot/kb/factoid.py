"""Factoid data model for Infobot Reborn."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FactoidType(str, Enum):
    """Type of factoid relationship."""

    IS = "is"  # Singular form: "X is Y"
    ARE = "are"  # Plural form: "X are Y"


@dataclass
class Factoid:
    """Represents a factoid in the knowledge base.

    Factoids are the core knowledge units inherited from the original Infobot.
    They store key-value mappings with support for special formatting.

    Special formatting support:
    - <reply>text: Bot responds with just the text (no "X is Y" prefix)
    - <action>text: Bot performs an action (e.g., "/me does something")
    - A|B|C: Pipe-separated random selection (bot picks one at random)
    - $who: Variable substitution for the asking user's name
    - $date: Variable substitution for current date/time

    Attributes:
        key: The factoid key/trigger phrase.
        value: The factoid value/response.
        factoid_type: Whether key is singular (is) or plural (are).
        created_at: When the factoid was created.
        updated_at: When the factoid was last modified.
        source: Optional attribution (username, channel, etc).
    """

    key: str
    value: str
    factoid_type: FactoidType
    created_at: datetime | None = None
    updated_at: datetime | None = None
    source: str | None = None

    def __post_init__(self) -> None:
        """Validate factoid data."""
        if not self.key or not self.key.strip():
            raise ValueError("Factoid key cannot be empty")
        if not self.value or not self.value.strip():
            raise ValueError("Factoid value cannot be empty")

        # Normalize key to lowercase for case-insensitive lookups
        self.key = self.key.strip().lower()
        self.value = self.value.strip()

        # Convert string to FactoidType if needed
        if isinstance(self.factoid_type, str):
            self.factoid_type = FactoidType(self.factoid_type.lower())

    @property
    def has_reply_tag(self) -> bool:
        """Check if factoid uses <reply> formatting."""
        return self.value.startswith("<reply>")

    @property
    def has_action_tag(self) -> bool:
        """Check if factoid uses <action> formatting."""
        return self.value.startswith("<action>")

    @property
    def has_random_selection(self) -> bool:
        """Check if factoid has pipe-separated random choices."""
        return "|" in self.value and not (self.has_reply_tag or self.has_action_tag)

    def to_dict(self) -> dict:
        """Convert factoid to dictionary representation.

        Returns:
            Dictionary with factoid data suitable for database storage.
        """
        return {
            "key": self.key,
            "value": self.value,
            "type": self.factoid_type.value,
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Factoid":
        """Create factoid from dictionary representation.

        Args:
            data: Dictionary with factoid data from database.

        Returns:
            Factoid instance.
        """
        return cls(
            key=data["key"],
            value=data["value"],
            factoid_type=FactoidType(data["type"]),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else None
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else None
            ),
            source=data.get("source"),
        )
