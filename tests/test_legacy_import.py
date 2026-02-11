"""Tests for legacy factoid import functionality."""

import logging
import random
from pathlib import Path

import pytest

import infobot.tools.legacy_import as legacy_import
from infobot.kb.factoid import FactoidType
from infobot.kb.store import FactoidStore
from infobot.tools.legacy_import import (
    DEFAULT_LEGACY_IMPORT_RNG_SEED,
    DEFAULT_LEGACY_IMPORT_SAMPLE_CAP,
    ImportStats,
    QualitySample,
    ThresholdGuidance,
    build_quality_rng,
    build_quality_sample,
    build_threshold_guidance,
    calculate_quality_average,
    calculate_quality_score,
    clean_irc_formatting,
    compute_quality_percentiles,
    configure_import_logging,
    emit_quality_diagnostics,
    format_quality_histogram,
    format_quality_sample_previews,
    get_quality_bucket_index,
    import_factoid_file,
    import_legacy_data,
    parse_factoid_line,
    record_quality_sample,
    refresh_quality_percentiles,
    render_import_summary,
    resolve_legacy_import_rng_seed,
    resolve_legacy_import_sample_cap,
    should_emit_quality_diagnostics,
    update_quality_aggregates,
    validate_diagnostic_cadence,
    validate_quality_threshold,
)


def test_clean_irc_formatting_bold():
    """Test cleaning bold IRC formatting."""
    assert clean_irc_formatting("\x02bold text\x02") == "**bold text**"
    assert (
        clean_irc_formatting("normal \x02bold\x02 normal") == "normal **bold** normal"
    )


def test_clean_irc_formatting_italic():
    """Test cleaning italic IRC formatting."""
    assert clean_irc_formatting("\x1ditalic text\x1d") == "*italic text*"


def test_clean_irc_formatting_underline():
    """Test cleaning underline IRC formatting."""
    assert clean_irc_formatting("\x1funderline text\x1f") == "__underline text__"


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
    text = "\x02bold\x02 and \x1ditalic\x1d and \x0304color"
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
    test_file.write_text("test => \x02bold text\x02 and \x1ditalic\x1d\n")

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
async def test_import_legacy_data_uses_shared_quality_stats(tmp_path: Path, db_conn):
    """IS/ARE imports should accumulate into one shared telemetry snapshot."""
    (tmp_path / "shared-is.txt").write_text(
        "alpha => first value with enough length\n"
        "beta => second value with enough length\n"
    )
    (tmp_path / "shared-are.txt").write_text(
        "gamma => third value with enough length\n"
        "delta => fourth value with enough length\n"
    )

    db_path = Path(db_conn.db_path)

    stats = await import_legacy_data(
        source_dir=tmp_path,
        db_path=db_path,
        botname="shared",
        quality_threshold=0.0,
    )

    assert stats.parsed == 4
    assert stats.quality_observations == 4
    assert stats.accepted_candidates == 4
    assert stats.rejected_candidates == 0
    assert sum(stats.quality_buckets) == stats.quality_observations
    assert stats.quality_p50 is not None
    assert stats.quality_p95 is not None
    source_files = {sample.source_file for sample in stats.accepted_samples}
    assert source_files == {"shared-is.txt", "shared-are.txt"}


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


def test_resolve_legacy_import_sample_cap_defaults(monkeypatch) -> None:
    """Sample cap should default when env var is absent."""
    monkeypatch.delenv("LEGACY_IMPORT_SAMPLE_CAP", raising=False)
    assert resolve_legacy_import_sample_cap() == DEFAULT_LEGACY_IMPORT_SAMPLE_CAP


def test_resolve_legacy_import_sample_cap_from_env(monkeypatch) -> None:
    """Sample cap should read integer env override."""
    monkeypatch.setenv("LEGACY_IMPORT_SAMPLE_CAP", "7")
    assert resolve_legacy_import_sample_cap() == 7


@pytest.mark.parametrize("raw_value", ["abc", "-1"])
def test_resolve_legacy_import_sample_cap_invalid_env(
    monkeypatch, raw_value: str
) -> None:
    """Sample cap env validation should reject malformed values."""
    monkeypatch.setenv("LEGACY_IMPORT_SAMPLE_CAP", raw_value)
    with pytest.raises(ValueError, match=r"LEGACY_IMPORT_SAMPLE_CAP"):
        resolve_legacy_import_sample_cap()


def test_resolve_legacy_import_rng_seed_defaults(monkeypatch) -> None:
    """RNG seed should default when env var is absent."""
    monkeypatch.delenv("LEGACY_IMPORT_RNG_SEED", raising=False)
    assert resolve_legacy_import_rng_seed() == DEFAULT_LEGACY_IMPORT_RNG_SEED


def test_resolve_legacy_import_rng_seed_from_env(monkeypatch) -> None:
    """RNG seed should read integer env override."""
    monkeypatch.setenv("LEGACY_IMPORT_RNG_SEED", "11")
    assert resolve_legacy_import_rng_seed() == 11


def test_resolve_legacy_import_rng_seed_invalid_env(monkeypatch) -> None:
    """RNG seed env validation should reject malformed values."""
    monkeypatch.setenv("LEGACY_IMPORT_RNG_SEED", "seed")
    with pytest.raises(ValueError, match=r"LEGACY_IMPORT_RNG_SEED"):
        resolve_legacy_import_rng_seed()


def test_build_quality_rng_is_deterministic(monkeypatch) -> None:
    """Helper should produce deterministic RNG instances for same seed."""
    monkeypatch.setenv("LEGACY_IMPORT_RNG_SEED", "5")
    first = build_quality_rng()
    second = build_quality_rng()
    assert first.random() == second.random()


@pytest.mark.parametrize(
    ("score", "expected_bucket"),
    [
        (-0.1, 0),
        (0.0, 0),
        (0.099, 0),
        (0.1, 1),
        (0.55, 5),
        (0.999, 9),
        (1.0, 9),
        (2.0, 9),
    ],
)
def test_get_quality_bucket_index(score: float, expected_bucket: int) -> None:
    """Score-to-bucket mapping should clamp and bin as expected."""
    assert get_quality_bucket_index(score) == expected_bucket


def test_update_quality_aggregates_tracks_counts() -> None:
    """Aggregate helper should update counters and histogram."""
    stats = ImportStats()
    update_quality_aggregates(stats, quality_score=0.2, accepted=False)
    update_quality_aggregates(stats, quality_score=0.8, accepted=True)

    assert stats.quality_observations == 2
    assert stats.quality_score_sum == pytest.approx(1.0)
    assert stats.accepted_candidates == 1
    assert stats.rejected_candidates == 1
    assert stats.quality_min == 0.2
    assert stats.quality_max == 0.8
    assert sum(stats.quality_buckets) == 2


def test_build_quality_sample_truncates_preview() -> None:
    """Quality sample preview should collapse whitespace and truncate."""
    sample = build_quality_sample(
        source_file="facts.txt",
        line_number=4,
        key="python",
        value="   value with   extra   spaces   ",
        quality_score=0.6,
        preview_chars=5,
    )
    assert sample.value_preview == "value..."
    assert sample.score == 0.6


def test_record_quality_sample_uses_reservoir_sampling() -> None:
    """Reservoir sampling should stay bounded and deterministic by seed."""

    def collect_sample_keys(seed: int) -> list[str]:
        local_stats = ImportStats()
        local_rng = random.Random(seed)
        for idx in range(25):
            update_quality_aggregates(local_stats, quality_score=0.7, accepted=True)
            record_quality_sample(
                stats=local_stats,
                sample=QualitySample(
                    source_file="facts.txt",
                    line_number=idx + 1,
                    key=f"key-{idx}",
                    value_preview=f"value-{idx}",
                    score=0.7,
                ),
                accepted=True,
                sample_cap=5,
                rng=local_rng,
            )
        return [sample.key for sample in local_stats.accepted_samples]

    first = collect_sample_keys(1234)
    second = collect_sample_keys(1234)
    assert len(first) == 5
    assert first == second


def test_compute_quality_percentiles_handles_empty_and_clustered() -> None:
    """Percentile helper should handle no data and clustered buckets."""
    assert compute_quality_percentiles([0] * 10) == {
        50: None,
        75: None,
        90: None,
        95: None,
    }

    clustered = [0, 0, 0, 0, 0, 10, 0, 0, 0, 0]
    percentile_values = compute_quality_percentiles(clustered)
    assert percentile_values[50] is not None
    assert percentile_values[50] >= 0.5
    assert percentile_values[95] <= 0.6


def test_refresh_quality_percentiles_and_average() -> None:
    """Stats percentile fields and average should derive from buckets/sum."""
    stats = ImportStats(
        quality_observations=4,
        quality_score_sum=2.0,
        quality_buckets=[0, 0, 1, 1, 1, 1, 0, 0, 0, 0],
    )
    refresh_quality_percentiles(stats)
    assert calculate_quality_average(stats) == 0.5
    assert stats.quality_p50 is not None
    assert stats.quality_p95 is not None


def test_format_quality_histogram() -> None:
    """Histogram formatter should emit bucket labels and percentages."""
    rendered = format_quality_histogram([1, 0, 0, 0, 0, 0, 0, 0, 0, 1])
    assert "0.0-0.1:1 (50.0%)" in rendered
    assert "0.9-1.0:1 (50.0%)" in rendered


def test_validate_diagnostic_cadence_rejects_invalid_values() -> None:
    """Diagnostic cadence validation should reject non-positive values."""
    with pytest.raises(ValueError, match=r"diagnostic_parsed_interval"):
        validate_diagnostic_cadence(parsed_interval=0, seconds_interval=1.0)

    with pytest.raises(ValueError, match=r"diagnostic_seconds_interval"):
        validate_diagnostic_cadence(parsed_interval=10, seconds_interval=0.0)


def test_should_emit_quality_diagnostics_cadence() -> None:
    """Diagnostics should trigger by parsed cadence or elapsed time."""
    stats = ImportStats(parsed=10)

    assert not should_emit_quality_diagnostics(
        stats=stats,
        parsed_since_last=0,
        elapsed_seconds=60.0,
        parsed_interval=5,
        seconds_interval=30.0,
    )
    assert should_emit_quality_diagnostics(
        stats=stats,
        parsed_since_last=5,
        elapsed_seconds=0.1,
        parsed_interval=5,
        seconds_interval=30.0,
    )
    assert should_emit_quality_diagnostics(
        stats=stats,
        parsed_since_last=1,
        elapsed_seconds=31.0,
        parsed_interval=5,
        seconds_interval=30.0,
    )


def test_format_quality_sample_previews() -> None:
    """Sample preview rendering should be bounded and deterministic."""
    samples = [
        QualitySample(
            source_file="facts.txt",
            line_number=2,
            key="zeta",
            value_preview="second",
            score=0.2,
        ),
        QualitySample(
            source_file="facts.txt",
            line_number=1,
            key="alpha",
            value_preview="first",
            score=0.9,
        ),
    ]

    rendered = format_quality_sample_previews(samples, limit=1)
    assert rendered.startswith("alpha@1")
    assert "score=0.90" in rendered
    assert format_quality_sample_previews([]) == "none"


def test_emit_quality_diagnostics_logs_expected_fields(caplog) -> None:
    """Diagnostics logging should include histogram and sample previews."""
    stats = ImportStats(
        parsed=4,
        imported=2,
        quality_observations=4,
        quality_score_sum=2.0,
        quality_min=0.1,
        quality_max=0.9,
        quality_buckets=[1, 0, 1, 0, 1, 1, 0, 0, 0, 0],
        accepted_candidates=3,
        rejected_candidates=1,
        accepted_samples=[
            QualitySample(
                source_file="facts-is.txt",
                line_number=1,
                key="alpha",
                value_preview="first",
                score=0.8,
            )
        ],
        rejected_samples=[
            QualitySample(
                source_file="facts-is.txt",
                line_number=2,
                key="beta",
                value_preview="second",
                score=0.2,
            )
        ],
    )

    module_logger = logging.getLogger("infobot.tools.legacy_import")
    module_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="infobot.tools.legacy_import"):
            emit_quality_diagnostics(
                stats=stats,
                file_path=Path("facts-is.txt"),
                factoid_type=FactoidType.IS,
                quality_threshold=0.3,
            )
    finally:
        module_logger.removeHandler(caplog.handler)

    log_text = caplog.text
    assert "Quality diagnostics [is/facts-is.txt]" in log_text
    assert "reject_rate=25.0%" in log_text
    assert "hist=0.0-0.1:1" in log_text
    assert "Accepted sample previews [is/facts-is.txt]" in log_text
    assert "alpha@1" in log_text
    assert "Rejected sample previews [is/facts-is.txt]" in log_text
    assert "beta@2" in log_text


def test_build_threshold_guidance_low_confidence() -> None:
    """Guidance should gate recommendations on sample size."""
    stats = ImportStats()
    guidance = build_threshold_guidance(
        stats,
        quality_threshold=0.3,
        min_sample_size=10,
    )
    assert isinstance(guidance, ThresholdGuidance)
    assert guidance.confidence == "low"
    assert guidance.suggested_threshold is None


def test_build_threshold_guidance_high_reject_rate() -> None:
    """Guidance should suggest lowering threshold for high reject rates."""
    stats = ImportStats()
    for _ in range(90):
        update_quality_aggregates(stats, quality_score=0.2, accepted=False)
    for _ in range(10):
        update_quality_aggregates(stats, quality_score=0.9, accepted=True)

    guidance = build_threshold_guidance(
        stats,
        quality_threshold=0.8,
        min_sample_size=20,
    )
    assert isinstance(guidance, ThresholdGuidance)
    assert guidance.confidence == "medium"
    assert guidance.suggested_threshold is not None
    assert guidance.suggested_threshold <= 0.8


def test_render_import_summary_includes_quality_sections_and_guardrail() -> None:
    """Summary output should include quality sections and low-confidence guardrail."""
    stats = ImportStats(
        total_lines=6,
        parsed=4,
        skipped_invalid=2,
        skipped_low_quality=1,
        imported=3,
        duplicates=0,
        errors=0,
        quality_observations=4,
        quality_score_sum=2.4,
        quality_min=0.2,
        quality_max=0.9,
        quality_buckets=[1, 0, 1, 0, 1, 1, 0, 0, 0, 0],
        accepted_candidates=3,
        rejected_candidates=1,
        accepted_samples=[
            QualitySample(
                source_file="facts-is.txt",
                line_number=1,
                key="alpha",
                value_preview="first",
                score=0.8,
            )
        ],
        rejected_samples=[
            QualitySample(
                source_file="facts-are.txt",
                line_number=2,
                key="beta",
                value_preview="second",
                score=0.2,
            )
        ],
    )
    refresh_quality_percentiles(stats)

    lines = render_import_summary(
        stats=stats,
        quality_threshold=0.3,
        guidance_min_sample_size=50,
    )

    rendered = "\n".join(lines)
    assert "IMPORT SUMMARY" in rendered
    assert "QUALITY METRICS" in rendered
    assert "Percentiles:" in rendered
    assert "Histogram:" in rendered
    assert "Bucket distribution:" in rendered
    assert "0.0-0.1:" in rendered
    assert "0.9-1.0:" in rendered
    assert "Accepted samples:" in rendered
    assert "Rejected samples:" in rendered
    assert "Threshold guidance:" in rendered
    assert "Guardrail: recommendation withheld" in rendered


@pytest.mark.asyncio
async def test_import_factoid_file_populates_quality_telemetry(
    tmp_path: Path,
    store: FactoidStore,
) -> None:
    """Import should update quality counters, buckets, percentiles, samples."""
    test_file = tmp_path / "telemetry-is.txt"
    test_file.write_text(
        "python => a high level programming language\n"
        "short => hi\n"
        "docs => see https://example.com/reference for docs\n"
        "invalid line\n"
    )

    stats = await import_factoid_file(
        test_file,
        FactoidType.IS,
        store,
        quality_threshold=0.5,
        sample_cap=2,
        rng=random.Random(99),
    )

    assert stats.quality_observations == stats.parsed
    assert stats.rejected_candidates >= 1
    assert stats.accepted_candidates >= 1
    assert stats.accepted_candidates + stats.rejected_candidates == stats.parsed
    assert sum(stats.quality_buckets) == stats.quality_observations
    assert len(stats.accepted_samples) <= 2
    assert len(stats.rejected_samples) <= 2
    assert stats.quality_p50 is not None
    assert stats.quality_p95 is not None


@pytest.mark.asyncio
async def test_import_factoid_file_emits_periodic_diagnostics_by_parsed_cadence(
    tmp_path: Path,
    store: FactoidStore,
    monkeypatch,
) -> None:
    """Import should emit diagnostics when parsed cadence threshold is met."""
    test_file = tmp_path / "diagnostic-parsed-is.txt"
    test_file.write_text(
        "a => fact one\n"
        "b => fact two\n"
        "c => fact three\n"
        "d => fact four\n"
        "e => fact five\n"
    )

    emit_calls: list[int] = []

    def fake_emit(**_kwargs: object) -> None:
        emit_calls.append(1)

    monkeypatch.setattr(legacy_import, "emit_quality_diagnostics", fake_emit)

    stats = await import_factoid_file(
        test_file,
        FactoidType.IS,
        store,
        quality_threshold=0.0,
        diagnostic_parsed_interval=2,
        diagnostic_seconds_interval=9999.0,
        monotonic_clock=lambda: 0.0,
    )

    assert stats.parsed == 5
    assert len(emit_calls) == 2


@pytest.mark.asyncio
async def test_import_factoid_file_emits_periodic_diagnostics_by_time_cadence(
    tmp_path: Path,
    store: FactoidStore,
    monkeypatch,
) -> None:
    """Import should emit diagnostics when elapsed monotonic time crosses threshold."""
    test_file = tmp_path / "diagnostic-time-is.txt"
    test_file.write_text("a => one\n" "b => two\n" "c => three\n")

    emit_calls: list[int] = []

    def fake_emit(**_kwargs: object) -> None:
        emit_calls.append(1)

    monotonic_values = iter([0.0, 0.4, 1.2, 1.4])

    monkeypatch.setattr(legacy_import, "emit_quality_diagnostics", fake_emit)

    stats = await import_factoid_file(
        test_file,
        FactoidType.IS,
        store,
        quality_threshold=0.0,
        diagnostic_parsed_interval=100,
        diagnostic_seconds_interval=1.0,
        monotonic_clock=lambda: next(monotonic_values),
    )

    assert stats.parsed == 3
    assert len(emit_calls) == 1
