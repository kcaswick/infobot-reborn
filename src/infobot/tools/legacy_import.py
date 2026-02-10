"""Import legacy Infobot factoid files into Infobot Reborn.

This module provides functionality to parse and import factoid data from
legacy Infobot installations (botname-is.txt, botname-are.txt format).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from infobot.db.connection import DatabaseConnection
from infobot.db.schema import initialize_schema
from infobot.kb.factoid import Factoid, FactoidType
from infobot.kb.store import FactoidExistsError, FactoidStore

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    """Statistics from an import operation."""

    total_lines: int = 0
    parsed: int = 0
    skipped_invalid: int = 0
    skipped_low_quality: int = 0
    imported: int = 0
    duplicates: int = 0
    errors: int = 0


def clean_irc_formatting(text: str) -> str:
    """Convert IRC formatting codes to Markdown and remove control characters.

    Args:
        text: Text with IRC formatting codes.

    Returns:
        Cleaned text with Markdown formatting.
    """
    # Bold: \x02text\x02 -> **text**
    text = re.sub(r"\x02([^\x02]*?)\x02", r"**\1**", text)

    # Italic: \x1D text\x1D -> *text*
    text = re.sub(r"\x1D([^\x1D]*?)\x1D", r"*\1*", text)

    # Underline: \x1Ftext\x1F -> __text__
    text = re.sub(r"\x1F([^\x1F]*?)\x1F", r"__\1__", text)

    # Remove color codes: \x03nn,mm or \x03nn
    text = re.sub(r"\x03\d+(?:,\d+)?", "", text)

    # Remove any remaining control characters (except newlines and tabs)
    # Do this AFTER format conversions to clean up orphaned control codes
    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", text)

    return text.strip()


def calculate_quality_score(key: str, value: str) -> float:
    """Calculate a quality score for a factoid using heuristics.

    Args:
        key: The factoid key/topic.
        value: The factoid value/information.

    Returns:
        Quality score between 0.0 and 1.0.
    """
    score = 0.5  # Start at neutral

    # Penalize very short content
    if len(value) < 3:
        score -= 0.4
    elif len(value) < 10:
        score -= 0.2

    # Penalize very long content (likely conversational noise)
    if len(value) > 500:
        score -= 0.3
    elif len(value) > 200:
        score -= 0.1

    # Reward reasonable content length
    if 10 <= len(value) <= 200:
        score += 0.2

    # Penalize keys that look like sentence fragments
    if key.count(" ") > 10:
        score -= 0.3

    # Penalize keys that end with punctuation (likely fragments)
    if key.rstrip().endswith(("?", "!", ".", ",")):
        score -= 0.2

    # Penalize values that start with conversational patterns
    conversational_patterns = [
        r"^(yeah|yep|nope|nah|ok|okay|sure|whatever)\b",
        r"^(lol|haha|heh|rofl|lmao)\b",
        r"^(hmm|umm|uh|er)\b",
    ]
    for pattern in conversational_patterns:
        if re.search(pattern, value.lower()):
            score -= 0.3
            break

    # Reward URLs (likely useful references)
    if "http://" in value or "https://" in value:
        score += 0.2

    # Penalize excessive special characters
    special_chars = sum(
        1 for c in value if not c.isalnum() and c not in " .,!?-"
    )
    special_char_ratio = special_chars / max(len(value), 1)
    if special_char_ratio > 0.3:
        score -= 0.2

    return max(0.0, min(1.0, score))


def parse_factoid_line(line: str) -> tuple[str, str] | None:
    """Parse a single factoid line in 'topic => information' format.

    Args:
        line: Line from factoid file.

    Returns:
        Tuple of (key, value) if valid, None otherwise.
    """
    if "=>" not in line:
        return None

    try:
        key, value = line.split("=>", 1)
        # Strip only whitespace, not control chars (IRC formatting needs them)
        key = key.strip(" \t\r\n")
        value = value.strip(" \t\r\n")

        if not key or not value:
            return None

        return (key, value)
    except Exception:
        return None


async def import_factoid_file(
    file_path: Path,
    factoid_type: FactoidType,
    store: FactoidStore,
    quality_threshold: float = 0.3,
) -> ImportStats:
    """Import a legacy factoid file into the database.

    Args:
        file_path: Path to the factoid file.
        factoid_type: Type of factoids (IS or ARE).
        store: FactoidStore instance for database operations.
        quality_threshold: Minimum quality score to import (0.0-1.0).

    Returns:
        ImportStats with import statistics.
    """
    stats = ImportStats()
    logger.info(f"Importing {factoid_type.value} factoids from {file_path}")

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return stats

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for line_num, line in enumerate(f, 1):
                stats.total_lines += 1
                # Strip only whitespace, preserve IRC formatting control chars
                line = line.strip(" \t\r\n")

                if not line:
                    continue

                # Parse the line
                result = parse_factoid_line(line)
                if result is None:
                    stats.skipped_invalid += 1
                    logger.debug(f"Invalid line format at {file_path}:{line_num}")
                    continue

                key, value = result
                stats.parsed += 1

                # Clean IRC formatting
                key = clean_irc_formatting(key)
                value = clean_irc_formatting(value)

                # Calculate quality score
                quality_score = calculate_quality_score(key, value)
                if quality_score < quality_threshold:
                    stats.skipped_low_quality += 1
                    logger.debug(
                        f"Low quality factoid (score={quality_score:.2f}): {key[:50]}"
                    )
                    continue

                # Create and import factoid
                try:
                    factoid = Factoid(
                        key=key,
                        value=value,
                        factoid_type=factoid_type,
                        source=f"legacy:{file_path.name}",
                    )
                    await store.create(factoid)
                    stats.imported += 1

                    if stats.imported % 100 == 0:
                        logger.info(f"Imported {stats.imported} factoids so far...")

                except FactoidExistsError:
                    stats.duplicates += 1
                    logger.debug(f"Duplicate factoid: {key}")
                except ValueError as e:
                    stats.errors += 1
                    logger.warning(
                        f"Error creating factoid at {file_path}:{line_num}: {e}"
                    )
                except Exception as e:
                    stats.errors += 1
                    logger.error(f"Unexpected error at {file_path}:{line_num}: {e}")

    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        stats.errors += 1

    return stats


async def import_legacy_data(
    source_dir: Path,
    db_path: Path,
    botname: str | None = None,
    quality_threshold: float = 0.3,
) -> ImportStats:
    """Import all legacy factoid files from a directory.

    Args:
        source_dir: Directory containing legacy factoid files.
        db_path: Path to SQLite database file.
        botname: Bot name to look for (e.g., 'infobot'). If None, auto-detect.
        quality_threshold: Minimum quality score to import (0.0-1.0).

    Returns:
        Combined ImportStats for all files.
    """
    logger.info(f"Starting legacy import from {source_dir}")
    logger.info(f"Database: {db_path}")
    logger.info(f"Quality threshold: {quality_threshold}")

    # Find factoid files
    if botname:
        is_file = source_dir / f"{botname}-is.txt"
        are_file = source_dir / f"{botname}-are.txt"
    else:
        # Auto-detect by looking for *-is.txt and *-are.txt files
        is_files = list(source_dir.glob("*-is.txt"))
        are_files = list(source_dir.glob("*-are.txt"))

        if not is_files and not are_files:
            raise FileNotFoundError(f"No factoid files found in {source_dir}")

        is_file = is_files[0] if is_files else None
        are_file = are_files[0] if are_files else None

        if is_file:
            logger.info(f"Auto-detected IS file: {is_file.name}")
        if are_file:
            logger.info(f"Auto-detected ARE file: {are_file.name}")

    # Initialize database
    conn = DatabaseConnection(db_path)
    await conn.connect()
    await initialize_schema(conn)
    store = FactoidStore(conn)

    # Import files
    total_stats = ImportStats()

    try:
        if is_file and is_file.exists():
            is_stats = await import_factoid_file(
                is_file, FactoidType.IS, store, quality_threshold
            )
            total_stats.total_lines += is_stats.total_lines
            total_stats.parsed += is_stats.parsed
            total_stats.skipped_invalid += is_stats.skipped_invalid
            total_stats.skipped_low_quality += is_stats.skipped_low_quality
            total_stats.imported += is_stats.imported
            total_stats.duplicates += is_stats.duplicates
            total_stats.errors += is_stats.errors

        if are_file and are_file.exists():
            are_stats = await import_factoid_file(
                are_file, FactoidType.ARE, store, quality_threshold
            )
            total_stats.total_lines += are_stats.total_lines
            total_stats.parsed += are_stats.parsed
            total_stats.skipped_invalid += are_stats.skipped_invalid
            total_stats.skipped_low_quality += are_stats.skipped_low_quality
            total_stats.imported += are_stats.imported
            total_stats.duplicates += are_stats.duplicates
            total_stats.errors += are_stats.errors

    finally:
        await conn.close()

    return total_stats


def main() -> None:
    """CLI entry point for legacy import tool."""
    parser = argparse.ArgumentParser(
        description="Import legacy Infobot factoid files into Infobot Reborn"
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory containing legacy factoid files",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/infobot.db"),
        help="Path to SQLite database (default: data/infobot.db)",
    )
    parser.add_argument(
        "--botname",
        type=str,
        help="Bot name to look for (e.g., 'infobot'). If not specified, auto-detect.",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.3,
        help="Minimum quality score to import (0.0-1.0, default: 0.3)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run import
    stats = asyncio.run(
        import_legacy_data(
            source_dir=args.source,
            db_path=args.database,
            botname=args.botname,
            quality_threshold=args.quality_threshold,
        )
    )

    # Print summary
    print("\n" + "=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"Total lines processed:    {stats.total_lines}")
    print(f"Successfully parsed:      {stats.parsed}")
    print(f"Skipped (invalid format): {stats.skipped_invalid}")
    print(f"Skipped (low quality):    {stats.skipped_low_quality}")
    print(f"Duplicates:               {stats.duplicates}")
    print(f"Errors:                   {stats.errors}")
    print(f"Successfully imported:    {stats.imported}")
    print("=" * 60)

    if stats.imported > 0:
        print(f"\n✓ Import complete! {stats.imported} factoids imported.")
    else:
        print("\n✗ No factoids were imported.")


if __name__ == "__main__":
    main()
