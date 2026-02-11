"""Tests for legacy factoid import functionality."""

import logging
from pathlib import Path

import pytest

from infobot.kb.factoid import FactoidType
from infobot.kb.store import FactoidStore
from infobot.tools.legacy_import import (
    calculate_quality_score,
    clean_irc_formatting,
    configure_import_logging,
    import_factoid_file,
    import_legacy_data,
    parse_factoid_line,
    validate_quality_threshold,
)


def test_clean_irc_formatting_bold():
    """Test cleaning bold IRC formatting."""
    assert clean_irc_formatting("\x02bold text\x02") == "**bold text**"
    assert (
        clean_irc_formatting("normal \x02bold\x02 normal")
        == "normal **bold** normal"
    )


def test_clean_irc_formatting_italic():
    """Test cleaning italic IRC formatting."""
    assert clean_irc_formatting("\x1Ditalic text\x1D") == "*italic text*"


def test_clean_irc_formatting_underline():
    """Test cleaning underline IRC formatting."""
    assert clean_irc_formatting("\x1Funderline text\x1F") == "__underline text__"


def test_clean_irc_formatting_color_codes():
    """Test removing IRC color codes."""
    assert clean_irc_formatting("\x0304red text") == "red text"
    assert clean_irc_formatting("\x0304,08red on yellow") == "red on yellow"


def test_clean_irc_formatting_control_chars():
    """Test removing other control characters."""
    text_with_controls = "hello\x07\x08world"
    assert clean_irc_formatting(text_with_controls) == "helloworld"


def test_clean_irc_formatting_combined():
    """Test cleaning multiple IRC formatting codes."""
    text = "\x02bold\x02 and \x1Ditalic\x1D and \x0304color"
    expected = "**bold** and *italic* and color"
    assert clean_irc_formatting(text) == expected


def test_parse_factoid_line_valid():
    """Test parsing a valid factoid line."""
    result = parse_factoid_line("python => a programming language")
    assert result is not None
    key, value = result
    assert key == "python"
    assert value == "a programming language"


def test_parse_factoid_line_with_whitespace():
    """Test parsing factoid line with extra whitespace."""
    result = parse_factoid_line("  python  =>  a programming language  ")
    assert result is not None
    key, value = result
    assert key == "python"
    assert value == "a programming language"


def test_parse_factoid_line_no_separator():
    """Test parsing line without separator."""
    assert parse_factoid_line("just some text") is None


def test_parse_factoid_line_empty_key():
    """Test parsing line with empty key."""
    assert parse_factoid_line(" => value only") is None


def test_parse_factoid_line_empty_value():
    """Test parsing line with empty value."""
    assert parse_factoid_line("key only => ") is None


def test_calculate_quality_score_good_factoid():
    """Test quality score for a good factoid."""
    score = calculate_quality_score("python", "a high-level programming language")
    assert score > 0.5


def test_calculate_quality_score_short_value():
    """Test quality score penalizes very short values."""
    score = calculate_quality_score("test", "hi")
    assert score < 0.5


def test_calculate_quality_score_conversational():
    """Test quality score penalizes conversational noise."""
    score = calculate_quality_score("something", "lol that's funny")
    assert score < 0.5


def test_calculate_quality_score_with_url():
    """Test quality score rewards URLs."""
    score_with_url = calculate_quality_score(
        "docs", "see https://example.com for more info"
    )
    score_without_url = calculate_quality_score("docs", "see the website for more info")
    assert score_with_url > score_without_url


def test_calculate_quality_score_sentence_fragment_key():
    """Test quality score penalizes keys that look like sentence fragments."""
    score = calculate_quality_score(
        "this is a really long key with many words that looks like a sentence",
        "some value",
    )
    assert score < 0.5


@pytest.mark.asyncio
async def test_import_factoid_file(tmp_path: Path, store: FactoidStore):
    """Test importing a factoid file."""
    # Create a test factoid file
    test_file = tmp_path / "test-is.txt"
    test_file.write_text(
        "python => a programming language\n"
        "ruby => another language\n"
        "invalid line without separator\n"
        "short => hi\n"  # Should be filtered by quality threshold
    )

    stats = await import_factoid_file(
        test_file, FactoidType.IS, store, quality_threshold=0.3
    )

    assert stats.total_lines == 4
    assert stats.parsed >= 2
    assert stats.imported >= 2
    assert stats.skipped_invalid >= 1

    # Verify imported factoids
    python = await store.get("python", FactoidType.IS)
    assert python is not None
    assert python.value == "a programming language"


@pytest.mark.asyncio
async def test_import_factoid_file_with_irc_formatting(
    tmp_path: Path, store: FactoidStore
):
    """Test that IRC formatting is cleaned during import."""
    test_file = tmp_path / "test-is.txt"
    test_file.write_text("test => \x02bold text\x02 and \x1Ditalic\x1D\n")

    stats = await import_factoid_file(test_file, FactoidType.IS, store)

    assert stats.imported == 1

    factoid = await store.get("test", FactoidType.IS)
    assert factoid is not None
    assert factoid.value == "**bold text** and *italic*"


@pytest.mark.asyncio
async def test_import_factoid_file_duplicates(tmp_path: Path, store: FactoidStore):
    """Test handling of duplicate factoids."""
    test_file = tmp_path / "test-is.txt"
    test_file.write_text("python => first definition\npython => second definition\n")

    stats = await import_factoid_file(test_file, FactoidType.IS, store)

    assert stats.imported == 1
    assert stats.duplicates == 1


@pytest.mark.asyncio
async def test_import_legacy_data_auto_detect(tmp_path: Path, db_conn):
    """Test auto-detecting botname from file names."""
    # Create test files
    (tmp_path / "testbot-is.txt").write_text("python => a language\n")
    (tmp_path / "testbot-are.txt").write_text("tests => important\n")

    db_path = Path(db_conn.db_path)

    stats = await import_legacy_data(
        source_dir=tmp_path,
        db_path=db_path,
        quality_threshold=0.3,
    )

    assert stats.imported >= 2


@pytest.mark.asyncio
async def test_import_legacy_data_specific_botname(tmp_path: Path, db_conn):
    """Test importing with specific botname."""
    # Create test files
    (tmp_path / "mybot-is.txt").write_text("python => a language\n")
    (tmp_path / "mybot-are.txt").write_text("tests => important\n")

    db_path = Path(db_conn.db_path)

    stats = await import_legacy_data(
        source_dir=tmp_path,
        db_path=db_path,
        botname="mybot",
        quality_threshold=0.3,
    )

    assert stats.imported >= 2


@pytest.mark.asyncio
async def test_import_legacy_data_no_files(tmp_path: Path, db_conn):
    """Test error handling when no factoid files found."""
    db_path = Path(db_conn.db_path)

    with pytest.raises(FileNotFoundError, match="No factoid files found"):
        await import_legacy_data(
            source_dir=tmp_path,
            db_path=db_path,
        )


@pytest.mark.parametrize("threshold", [0.0, 0.3, 1.0])
def test_validate_quality_threshold_valid(threshold: float) -> None:
    """Threshold validation accepts inclusive bounds."""
    validate_quality_threshold(threshold)


@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_validate_quality_threshold_invalid(threshold: float) -> None:
    """Threshold validation rejects out-of-range values."""
    with pytest.raises(
        ValueError, match=r"quality-threshold must be between 0.0 and 1.0"
    ):
        validate_quality_threshold(threshold)


@pytest.mark.asyncio
async def test_import_legacy_data_invalid_threshold_fails_fast(
    tmp_path: Path, db_conn
) -> None:
    """Invalid threshold is rejected before file scanning/import."""
    db_path = Path(db_conn.db_path)
    with pytest.raises(
        ValueError, match=r"quality-threshold must be between 0.0 and 1.0"
    ):
        await import_legacy_data(
            source_dir=tmp_path,
            db_path=db_path,
            quality_threshold=1.2,
        )


def test_configure_import_logging_idempotent_and_root_safe() -> None:
    """Module logging setup should be idempotent and avoid root pollution."""
    root_logger = logging.getLogger()
    root_handlers_before = tuple(root_logger.handlers)
    root_level_before = root_logger.level

    module_logger = logging.getLogger("infobot.tools.legacy_import")

    # Clean up tagged handlers from prior tests to ensure deterministic assertions.
    for handler in list(module_logger.handlers):
        if getattr(handler, "_legacy_import_handler", False):
            module_logger.removeHandler(handler)

    try:
        configure_import_logging(verbose=False)
        configure_import_logging(verbose=True)

        tagged_handlers = [
            handler
            for handler in module_logger.handlers
            if getattr(handler, "_legacy_import_handler", False)
        ]
        assert len(tagged_handlers) == 1
        assert module_logger.level == logging.DEBUG
        assert module_logger.propagate is False
        assert tuple(root_logger.handlers) == root_handlers_before
        assert root_logger.level == root_level_before
    finally:
        for handler in list(module_logger.handlers):
            if getattr(handler, "_legacy_import_handler", False):
                module_logger.removeHandler(handler)
