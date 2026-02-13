"""Import legacy Infobot factoid files into Infobot Reborn.

This module provides functionality to parse and import factoid data from
legacy Infobot installations (botname-is.txt, botname-are.txt format).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path

from infobot.db.connection import DatabaseConnection
from infobot.db.schema import initialize_schema
from infobot.kb.factoid import Factoid, FactoidType
from infobot.kb.store import FactoidExistsError, FactoidStore

logger = logging.getLogger(__name__)
LOGGER_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_LEGACY_IMPORT_HANDLER_TAG = "_legacy_import_handler"
QUALITY_BUCKET_COUNT = 10
QUALITY_PERCENTILES = (50, 75, 90, 95)
DEFAULT_LEGACY_IMPORT_SAMPLE_CAP = 20
DEFAULT_LEGACY_IMPORT_RNG_SEED = 1337
DEFAULT_QUALITY_SAMPLE_PREVIEW_CHARS = 96
DEFAULT_DIAGNOSTIC_PARSED_INTERVAL = 1000
DEFAULT_DIAGNOSTIC_SECONDS_INTERVAL = 30.0
DEFAULT_DIAGNOSTIC_SAMPLE_PREVIEW_LIMIT = 3


@dataclass(frozen=True)
class QualitySample:
    """A sampled factoid quality observation for diagnostics."""

    source_file: str
    line_number: int
    key: str
    value_preview: str
    score: float


@dataclass(frozen=True)
class ThresholdGuidance:
    """Preliminary quality-threshold tuning guidance."""

    current_threshold: float
    suggested_threshold: float | None
    confidence: str
    rationale: str


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
    quality_observations: int = 0
    quality_score_sum: float = 0.0
    quality_min: float | None = None
    quality_max: float | None = None
    quality_buckets: list[int] = field(
        default_factory=lambda: [0] * QUALITY_BUCKET_COUNT
    )
    quality_p50: float | None = None
    quality_p75: float | None = None
    quality_p90: float | None = None
    quality_p95: float | None = None
    accepted_candidates: int = 0
    rejected_candidates: int = 0
    accepted_samples: list[QualitySample] = field(default_factory=list)
    rejected_samples: list[QualitySample] = field(default_factory=list)


def resolve_legacy_import_sample_cap(sample_cap: int | None = None) -> int:
    """Resolve sampling reservoir cap from args or environment.

    Args:
        sample_cap: Optional override value.

    Returns:
        Effective sample cap.

    Raises:
        ValueError: If the value is invalid.
    """
    if sample_cap is None:
        raw_sample_cap = os.getenv("LEGACY_IMPORT_SAMPLE_CAP")
        if raw_sample_cap is None:
            sample_cap = DEFAULT_LEGACY_IMPORT_SAMPLE_CAP
        else:
            try:
                sample_cap = int(raw_sample_cap)
            except ValueError as e:
                raise ValueError(
                    "LEGACY_IMPORT_SAMPLE_CAP must be an integer "
                    f"(got {raw_sample_cap!r})"
                ) from e

    if sample_cap < 0:
        raise ValueError("LEGACY_IMPORT_SAMPLE_CAP must be >= 0 " f"(got {sample_cap})")

    return sample_cap


def resolve_legacy_import_rng_seed(rng_seed: int | None = None) -> int:
    """Resolve deterministic RNG seed from args or environment.

    Args:
        rng_seed: Optional override value.

    Returns:
        Effective RNG seed.

    Raises:
        ValueError: If the value is invalid.
    """
    if rng_seed is not None:
        return rng_seed

    raw_seed = os.getenv("LEGACY_IMPORT_RNG_SEED")
    if raw_seed is None:
        return DEFAULT_LEGACY_IMPORT_RNG_SEED

    try:
        return int(raw_seed)
    except ValueError as e:
        raise ValueError(
            "LEGACY_IMPORT_RNG_SEED must be an integer " f"(got {raw_seed!r})"
        ) from e


def build_quality_rng(rng_seed: int | None = None) -> random.Random:
    """Build deterministic RNG for quality sample reservoirs."""
    return random.Random(resolve_legacy_import_rng_seed(rng_seed))


def clamp_quality_score(quality_score: float) -> float:
    """Clamp a quality score into the inclusive [0.0, 1.0] range."""
    return max(0.0, min(1.0, quality_score))


def get_quality_bucket_index(quality_score: float) -> int:
    """Map quality score to one of 10 buckets in [0.0, 1.0]."""
    clamped_score = clamp_quality_score(quality_score)
    if clamped_score >= 1.0:
        return QUALITY_BUCKET_COUNT - 1
    return int(clamped_score * QUALITY_BUCKET_COUNT)


def get_quality_bucket_label(bucket_index: int) -> str:
    """Return the printable label for a bucket index."""
    if not 0 <= bucket_index < QUALITY_BUCKET_COUNT:
        raise ValueError(
            f"bucket_index must be in [0, {QUALITY_BUCKET_COUNT - 1}] "
            f"(got {bucket_index})"
        )

    lower = bucket_index / QUALITY_BUCKET_COUNT
    upper = (bucket_index + 1) / QUALITY_BUCKET_COUNT
    return f"{lower:.1f}-{upper:.1f}"


def update_quality_aggregates(
    stats: ImportStats,
    quality_score: float,
    accepted: bool,
) -> None:
    """Update aggregate quality counters and histogram buckets."""
    clamped_score = clamp_quality_score(quality_score)
    stats.quality_observations += 1
    stats.quality_score_sum += clamped_score
    stats.quality_min = (
        clamped_score
        if stats.quality_min is None
        else min(stats.quality_min, clamped_score)
    )
    stats.quality_max = (
        clamped_score
        if stats.quality_max is None
        else max(stats.quality_max, clamped_score)
    )
    stats.quality_buckets[get_quality_bucket_index(clamped_score)] += 1

    if accepted:
        stats.accepted_candidates += 1
    else:
        stats.rejected_candidates += 1


def build_quality_sample(
    source_file: str,
    line_number: int,
    key: str,
    value: str,
    quality_score: float,
    preview_chars: int = DEFAULT_QUALITY_SAMPLE_PREVIEW_CHARS,
) -> QualitySample:
    """Build a lightweight quality sample preview record."""
    compact_value = " ".join(value.split())
    if len(compact_value) > preview_chars:
        value_preview = f"{compact_value[:preview_chars]}..."
    else:
        value_preview = compact_value

    return QualitySample(
        source_file=source_file,
        line_number=line_number,
        key=key,
        value_preview=value_preview,
        score=clamp_quality_score(quality_score),
    )


def reservoir_sample_insert(
    reservoir: list[QualitySample],
    sample: QualitySample,
    population_seen: int,
    sample_cap: int,
    rng: random.Random,
) -> None:
    """Update a bounded reservoir using algorithm R."""
    if sample_cap <= 0:
        return

    if len(reservoir) < sample_cap:
        reservoir.append(sample)
        return

    replacement_index = rng.randrange(population_seen)
    if replacement_index < sample_cap:
        reservoir[replacement_index] = sample


def record_quality_sample(
    stats: ImportStats,
    sample: QualitySample,
    accepted: bool,
    sample_cap: int,
    rng: random.Random,
) -> None:
    """Record sample into accepted/rejected reservoir sets."""
    reservoir = stats.accepted_samples if accepted else stats.rejected_samples
    population_seen = (
        stats.accepted_candidates if accepted else stats.rejected_candidates
    )
    reservoir_sample_insert(
        reservoir=reservoir,
        sample=sample,
        population_seen=population_seen,
        sample_cap=sample_cap,
        rng=rng,
    )


def compute_quality_percentiles(
    bucket_counts: Sequence[int],
    percentiles: Sequence[int] = QUALITY_PERCENTILES,
) -> dict[int, float | None]:
    """Approximate percentile values from fixed-width histogram buckets."""
    if len(bucket_counts) != QUALITY_BUCKET_COUNT:
        raise ValueError(
            f"bucket_counts must have {QUALITY_BUCKET_COUNT} buckets "
            f"(got {len(bucket_counts)})"
        )

    total_samples = sum(bucket_counts)
    if total_samples == 0:
        return {percentile: None for percentile in percentiles}

    results: dict[int, float | None] = {}
    for percentile in percentiles:
        if not 0 <= percentile <= 100:
            raise ValueError(f"percentile must be in [0, 100] (got {percentile})")

        target_rank = max(1, ceil(total_samples * (percentile / 100)))
        cumulative = 0
        for bucket_index, bucket_count in enumerate(bucket_counts):
            cumulative += bucket_count
            if cumulative < target_rank:
                continue

            lower = bucket_index / QUALITY_BUCKET_COUNT
            upper = (bucket_index + 1) / QUALITY_BUCKET_COUNT
            previous = cumulative - bucket_count
            if bucket_count == 0:
                interpolated = upper
            else:
                position = (target_rank - previous) / bucket_count
                interpolated = lower + (upper - lower) * position

            results[percentile] = clamp_quality_score(interpolated)
            break

    return results


def refresh_quality_percentiles(stats: ImportStats) -> None:
    """Refresh percentile fields from the current histogram."""
    percentile_values = compute_quality_percentiles(stats.quality_buckets)
    stats.quality_p50 = percentile_values[50]
    stats.quality_p75 = percentile_values[75]
    stats.quality_p90 = percentile_values[90]
    stats.quality_p95 = percentile_values[95]


def calculate_quality_average(stats: ImportStats) -> float | None:
    """Return mean quality score or None when no observations exist."""
    if stats.quality_observations == 0:
        return None
    return stats.quality_score_sum / stats.quality_observations


def validate_diagnostic_cadence(
    parsed_interval: int,
    seconds_interval: float,
) -> None:
    """Validate periodic diagnostic cadence parameters."""
    if parsed_interval <= 0:
        raise ValueError(
            "diagnostic_parsed_interval must be > 0 " f"(got {parsed_interval})"
        )
    if seconds_interval <= 0:
        raise ValueError(
            "diagnostic_seconds_interval must be > 0 " f"(got {seconds_interval})"
        )


def should_emit_quality_diagnostics(
    stats: ImportStats,
    parsed_since_last: int,
    elapsed_seconds: float,
    parsed_interval: int,
    seconds_interval: float,
) -> bool:
    """Determine if periodic diagnostics should be emitted."""
    if stats.parsed == 0 or parsed_since_last <= 0:
        return False

    if parsed_since_last >= parsed_interval:
        return True

    return elapsed_seconds >= seconds_interval


def format_quality_sample_previews(
    samples: Sequence[QualitySample],
    limit: int = DEFAULT_DIAGNOSTIC_SAMPLE_PREVIEW_LIMIT,
) -> str:
    """Render sample previews as a compact, stable string."""
    if limit <= 0:
        raise ValueError(f"limit must be > 0 (got {limit})")

    if not samples:
        return "none"

    preview_items = sorted(
        samples,
        key=lambda sample: (sample.source_file, sample.line_number, sample.key),
    )[:limit]
    return " | ".join(
        (
            f"{sample.key}@{sample.line_number} "
            f"(score={sample.score:.2f}) -> {sample.value_preview}"
        )
        for sample in preview_items
    )


def emit_quality_diagnostics(
    stats: ImportStats,
    file_path: Path,
    factoid_type: FactoidType,
    quality_threshold: float,
) -> None:
    """Emit a periodic quality diagnostics snapshot."""
    quality_average = calculate_quality_average(stats)
    reject_rate = (
        stats.rejected_candidates / stats.quality_observations
        if stats.quality_observations
        else 0.0
    )
    histogram = format_quality_histogram(stats.quality_buckets)
    min_score = stats.quality_min if stats.quality_min is not None else 0.0
    max_score = stats.quality_max if stats.quality_max is not None else 0.0
    avg_score = quality_average if quality_average is not None else 0.0

    logger.info(
        "Quality diagnostics [%s/%s]: parsed=%d imported=%d rejected=%d "
        "reject_rate=%.1f%% threshold=%.2f score[min=%.2f avg=%.2f max=%.2f] "
        "hist=%s",
        factoid_type.value,
        file_path.name,
        stats.parsed,
        stats.imported,
        stats.rejected_candidates,
        reject_rate * 100,
        quality_threshold,
        min_score,
        avg_score,
        max_score,
        histogram,
    )
    logger.info(
        "Accepted sample previews [%s/%s]: %s",
        factoid_type.value,
        file_path.name,
        format_quality_sample_previews(stats.accepted_samples),
    )
    logger.info(
        "Rejected sample previews [%s/%s]: %s",
        factoid_type.value,
        file_path.name,
        format_quality_sample_previews(stats.rejected_samples),
    )


def format_quality_histogram(bucket_counts: Sequence[int]) -> str:
    """Format quality histogram as compact bucket summary text."""
    if len(bucket_counts) != QUALITY_BUCKET_COUNT:
        raise ValueError(
            f"bucket_counts must have {QUALITY_BUCKET_COUNT} buckets "
            f"(got {len(bucket_counts)})"
        )

    total_samples = sum(bucket_counts)
    if total_samples == 0:
        return "no samples"

    parts = []
    for bucket_index, count in enumerate(bucket_counts):
        percentage = (count / total_samples) * 100
        label = get_quality_bucket_label(bucket_index)
        parts.append(f"{label}:{count} ({percentage:.1f}%)")

    return " | ".join(parts)


def build_threshold_guidance(
    stats: ImportStats,
    quality_threshold: float,
    min_sample_size: int = 50,
) -> ThresholdGuidance:
    """Build threshold guidance scaffolding from observed score distribution."""
    validate_quality_threshold(quality_threshold)
    if min_sample_size <= 0:
        raise ValueError(f"min_sample_size must be > 0 (got {min_sample_size})")

    refresh_quality_percentiles(stats)

    if stats.quality_observations < min_sample_size:
        return ThresholdGuidance(
            current_threshold=quality_threshold,
            suggested_threshold=None,
            confidence="low",
            rationale=(
                "Insufficient scored candidates for recommendation "
                f"({stats.quality_observations}/{min_sample_size})."
            ),
        )

    reject_rate = (
        stats.rejected_candidates / stats.quality_observations
        if stats.quality_observations
        else 0.0
    )

    suggested_threshold = quality_threshold
    rationale = "Threshold appears balanced; keep current setting."

    if reject_rate > 0.80 and stats.quality_p50 is not None:
        suggested_threshold = round(stats.quality_p50, 2)
        rationale = "High reject rate observed; consider lowering threshold toward p50."
    elif reject_rate < 0.05 and stats.quality_p90 is not None:
        suggested_threshold = round(stats.quality_p90, 2)
        rationale = (
            "Very low reject rate observed; consider raising threshold toward p90."
        )

    return ThresholdGuidance(
        current_threshold=quality_threshold,
        suggested_threshold=suggested_threshold,
        confidence="medium",
        rationale=rationale,
    )


def _format_optional_score(value: float | None) -> str:
    """Format an optional score for summary output."""
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def render_sample_table(
    accepted_samples: Sequence[QualitySample],
    rejected_samples: Sequence[QualitySample],
    key_width: int = 45,
    value_width: int = 60,
) -> list[str]:
    """Render accepted/rejected samples as a markdown table sorted by score.

    Args:
        accepted_samples: Accepted sample records.
        rejected_samples: Rejected sample records.
        key_width: Column width for key.
        value_width: Column width for value.

    Returns:
        Lines of markdown table.
    """
    # Combine samples with status
    all_samples = [
        ("Accepted", sample) for sample in accepted_samples
    ] + [("Rejected", sample) for sample in rejected_samples]

    # Sort by score descending, then by key for stability
    all_samples.sort(
        key=lambda x: (-x[1].score, x[1].source_file, x[1].line_number, x[1].key)
    )

    # Remove duplicates (keep first occurrence)
    seen = set()
    unique_samples = []
    for status, sample in all_samples:
        key = (sample.key, sample.score, sample.value_preview)
        if key not in seen:
            seen.add(key)
            unique_samples.append((status, sample))

    if not unique_samples:
        return []

    lines = [
        f"| {'STATUS':<8} | {'KEY':<{key_width}} | {'SCORE':<6} | VALUE",
        f"|{'-' * 10}|{'-' * (key_width + 2)}|{'-' * 8}|{'-' * (value_width + 2)}",
    ]

    for status, sample in unique_samples:
        key_trunc = (
            sample.key[:key_width] if len(sample.key) > key_width else sample.key
        )
        value_trunc = (
            sample.value_preview[:value_width]
            if len(sample.value_preview) > value_width
            else sample.value_preview
        )
        lines.append(
            f"| {status:<8} | {key_trunc:<{key_width}} | {sample.score:<6.2f} | {value_trunc}"
        )

    return lines


def render_import_summary(
    stats: ImportStats,
    quality_threshold: float,
    guidance_min_sample_size: int = 50,
) -> list[str]:
    """Render complete import summary lines for CLI output."""
    validate_quality_threshold(quality_threshold)
    guidance = build_threshold_guidance(
        stats=stats,
        quality_threshold=quality_threshold,
        min_sample_size=guidance_min_sample_size,
    )
    quality_average = calculate_quality_average(stats)
    reject_rate = (
        stats.rejected_candidates / stats.quality_observations
        if stats.quality_observations
        else 0.0
    )

    lines = []

    # Add sample table if samples exist
    sample_table = render_sample_table(
        accepted_samples=stats.accepted_samples,
        rejected_samples=stats.rejected_samples,
    )
    if sample_table:
        lines.extend(["QUALITY SAMPLES (sorted by score)", ""] + sample_table + [""])

    lines.extend([
        "IMPORT SUMMARY",
        "=" * 60,
        f"Total lines processed:    {stats.total_lines}",
        f"Successfully parsed:      {stats.parsed}",
        f"Skipped (invalid format): {stats.skipped_invalid}",
        f"Skipped (low quality):    {stats.skipped_low_quality}",
        f"Duplicates:               {stats.duplicates}",
        f"Errors:                   {stats.errors}",
        f"Successfully imported:    {stats.imported}",
        "=" * 60,
        "QUALITY METRICS",
        "-" * 60,
        f"Scored candidates:        {stats.quality_observations}",
        f"Accepted candidates:      {stats.accepted_candidates}",
        f"Rejected candidates:      {stats.rejected_candidates}",
        f"Reject rate:              {reject_rate * 100:.1f}%",
        (
            "Score range/avg:          "
            f"min={_format_optional_score(stats.quality_min)} "
            f"avg={_format_optional_score(quality_average)} "
            f"max={_format_optional_score(stats.quality_max)}"
        ),
        (
            "Percentiles:              "
            f"p50={_format_optional_score(stats.quality_p50)} "
            f"p75={_format_optional_score(stats.quality_p75)} "
            f"p90={_format_optional_score(stats.quality_p90)} "
            f"p95={_format_optional_score(stats.quality_p95)}"
        ),
        "Histogram:                ",
    ])

    total_observations = stats.quality_observations
    for bucket_index, count in enumerate(stats.quality_buckets):
        bucket_label = get_quality_bucket_label(bucket_index)
        percentage = (count / total_observations * 100) if total_observations else 0.0
        lines.append(f"  {bucket_label}: {count} ({percentage:.1f}%)")

    lines.extend(
        [
            "Accepted samples:         "
            + format_quality_sample_previews(stats.accepted_samples),
            "Rejected samples:         "
            + format_quality_sample_previews(stats.rejected_samples),
            "Threshold guidance:",
            (
                f"  Current threshold={guidance.current_threshold:.2f} "
                f"Suggested={_format_optional_score(guidance.suggested_threshold)} "
                f"Confidence={guidance.confidence}"
            ),
            f"  Rationale: {guidance.rationale}",
        ]
    )

    if guidance.confidence == "low":
        lines.append(
            "  Guardrail: recommendation withheld until sample size is sufficient."
        )

    return lines


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
    key_has_conversational_signal = False

    # --- Key quality signals ---

    # Penalize keys that look like sentence fragments
    key_words = key.count(" ") + 1
    key_lower = key.lower()

    # Graduated penalty for wordy keys
    if key_words > 10:
        score -= 0.3
    elif key_words > 6:
        score -= 0.2
    elif key_words > 4:
        score -= 0.1

    # Penalize keys that end with punctuation (likely fragments)
    if key.rstrip().endswith(("?", "!", ".", ",")):
        score -= 0.2
        key_has_conversational_signal = True

    # Keys starting with interjections/filler
    if re.search(
        r"^(ack|ah|oh|hmm|hrm|hm|huh|hey|well|ugh|wow|yay|yeh|yeah|idk)\b",
        key_lower,
    ):
        score -= 0.2
        key_has_conversational_signal = True

    # Keys starting with first-person pronouns (personal narrative)
    if re.search(
        r"^(i\s|i'm|i'd|i'll|i've|you're)\b",
        key_lower,
    ):
        score -= 0.15
        key_has_conversational_signal = True

    # Keys starting with conjunctions/prepositions/adverbs (mid-sentence capture)
    if re.search(
        r"^(as|but|and|or|so|if|when|because|since|though|although"
        r"|while|after|before|until|from|like|maybe|only|just"
        r"|now|then|see|somehow)\b",
        key_lower,
    ):
        score -= 0.15
        key_has_conversational_signal = True

    # Commas in keys — graduated
    comma_count = key.count(",")
    if comma_count >= 2:
        score -= 0.25
        key_has_conversational_signal = True
    elif comma_count == 1:
        score -= 0.15
        key_has_conversational_signal = True

    # Ellipsis in keys (narrative/trailing thought)
    if "..." in key:
        score -= 0.15
        key_has_conversational_signal = True

    # Text emoticons in keys (o.o, O_O, x_x, etc.)
    if re.search(r"[oOxX0][._][oOxX0]|>_<|\^_\^", key):
        score -= 0.2
        key_has_conversational_signal = True

    # Conversational phrases in keys
    if re.search(
        r"\b(let me|let's|ask you|tell you|you know|i think|i thought"
        r"|issue|problem|thing|see that|working)\b",
        key_lower,
    ):
        score -= 0.2
        key_has_conversational_signal = True

    # Addressing someone
    if re.search(r"\b(bub|dude|man|mate|pal|buddy)\b", key_lower):
        score -= 0.2
        key_has_conversational_signal = True

    # Concise key bonus — short clean topic names are intentional
    if key_words <= 2 and not key_has_conversational_signal:
        score += 0.1

    # --- Value quality signals ---

    # Value length (reduced base reward)
    if len(value) < 3:
        score -= 0.35
    elif len(value) < 10:
        score -= 0.05  # Softened: short answers to clean keys are valid
    elif len(value) > 500:
        score -= 0.3
    elif len(value) > 200:
        score -= 0.1
    elif 10 <= len(value) <= 200:
        score += 0.1

    # Intentional factoid markers (HIGH value)
    if re.search(r"<(response|reply|action)>", value.lower()):
        score += 0.3

    # Penalize values that start with conversational patterns
    conversational_patterns = [
        r"^(yeah|yep|nope|nah|ok|okay|sure|whatever)\b",
        r"^(lol|haha|hehe?|rofl|lmao)\b",                         # laughter
        r"^(hmm|umm|uh|er|hrm|huh)\b",
        r"^(back|here|gone|away|around|busy|afk|brb)\b",        # IRC status
        r"^(not sure|no idea|dunno|idk|iirc)\b",                # uncertainty
        r"^(shy|afraid|sorry|glad|happy|sad)\s+to\b",           # emotional state
        r"^(really|actually|basically|literally)\s+\w+ing\b",   # intensifier + gerund
        r"\b(i'm|i am)\s+\w+ing\b",                             # first-person action
    ]
    for pattern in conversational_patterns:
        if re.search(pattern, value.lower()):
            score -= 0.3
            break

    # Reward URLs (likely useful references)
    if "http://" in value or "https://" in value:
        score += 0.2

    # Emoticons
    if re.search(r"[:;]['\-]?[)(DPpO/\\|]", value):
        score -= 0.1

    # Penalize excessive special characters
    special_chars = sum(1 for c in value if not c.isalnum() and c not in " .,!?-")
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


def configure_import_logging(verbose: bool) -> logging.Logger:
    """Configure module-scoped logging for legacy import CLI.

    This avoids mutating root logger configuration, which prevents dependency
    debug logs (e.g., aiosqlite) from flooding verbose output.

    Args:
        verbose: Whether debug-level logging should be enabled.

    Returns:
        Configured module logger.
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(log_level)
    logger.propagate = False

    # Remove previously configured module handlers to keep setup idempotent.
    for handler in list(logger.handlers):
        if getattr(handler, _LEGACY_IMPORT_HANDLER_TAG, False):
            logger.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(logging.Formatter(LOGGER_FORMAT))
    setattr(handler, _LEGACY_IMPORT_HANDLER_TAG, True)
    logger.addHandler(handler)
    return logger


def validate_quality_threshold(quality_threshold: float) -> None:
    """Validate quality threshold is in the inclusive range [0.0, 1.0].

    Args:
        quality_threshold: Threshold value to validate.

    Raises:
        ValueError: If quality threshold is outside [0.0, 1.0].
    """
    if not 0.0 <= quality_threshold <= 1.0:
        raise ValueError(
            "quality-threshold must be between 0.0 and 1.0 "
            f"(got {quality_threshold})"
        )


async def import_factoid_file(
    file_path: Path,
    factoid_type: FactoidType,
    store: FactoidStore,
    quality_threshold: float = 0.3,
    stats: ImportStats | None = None,
    sample_cap: int | None = None,
    rng: random.Random | None = None,
    diagnostic_parsed_interval: int = DEFAULT_DIAGNOSTIC_PARSED_INTERVAL,
    diagnostic_seconds_interval: float = DEFAULT_DIAGNOSTIC_SECONDS_INTERVAL,
    monotonic_clock: Callable[[], float] = time.monotonic,
) -> ImportStats:
    """Import a legacy factoid file into the database.

    Args:
        file_path: Path to the factoid file.
        factoid_type: Type of factoids (IS or ARE).
        store: FactoidStore instance for database operations.
        quality_threshold: Minimum quality score to import (0.0-1.0).
        stats: Optional stats accumulator.
        sample_cap: Optional reservoir sample cap override.
        rng: Optional deterministic RNG for sampling.
        diagnostic_parsed_interval: Parsed candidate cadence for diagnostics.
        diagnostic_seconds_interval: Time cadence for diagnostics.
        monotonic_clock: Clock function for elapsed-time checks.

    Returns:
        ImportStats with import statistics.
    """
    validate_quality_threshold(quality_threshold)
    validate_diagnostic_cadence(
        parsed_interval=diagnostic_parsed_interval,
        seconds_interval=diagnostic_seconds_interval,
    )
    resolved_sample_cap = resolve_legacy_import_sample_cap(sample_cap)
    quality_rng = rng if rng is not None else build_quality_rng()

    if stats is None:
        stats = ImportStats()
    last_diagnostic_parsed = stats.parsed
    last_diagnostic_mono = monotonic_clock()
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
                is_accepted = quality_score >= quality_threshold

                update_quality_aggregates(
                    stats=stats,
                    quality_score=quality_score,
                    accepted=is_accepted,
                )
                quality_sample = build_quality_sample(
                    source_file=file_path.name,
                    line_number=line_num,
                    key=key,
                    value=value,
                    quality_score=quality_score,
                )
                record_quality_sample(
                    stats=stats,
                    sample=quality_sample,
                    accepted=is_accepted,
                    sample_cap=resolved_sample_cap,
                    rng=quality_rng,
                )

                now_mono = monotonic_clock()
                parsed_since_last = stats.parsed - last_diagnostic_parsed
                elapsed_seconds = now_mono - last_diagnostic_mono
                if should_emit_quality_diagnostics(
                    stats=stats,
                    parsed_since_last=parsed_since_last,
                    elapsed_seconds=elapsed_seconds,
                    parsed_interval=diagnostic_parsed_interval,
                    seconds_interval=diagnostic_seconds_interval,
                ):
                    emit_quality_diagnostics(
                        stats=stats,
                        file_path=file_path,
                        factoid_type=factoid_type,
                        quality_threshold=quality_threshold,
                    )
                    last_diagnostic_parsed = stats.parsed
                    last_diagnostic_mono = now_mono

                if not is_accepted:
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

                    if stats.imported <= 2000 and stats.imported % 100 == 0 or stats.imported % 1000 == 0 :
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

    refresh_quality_percentiles(stats)
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
    validate_quality_threshold(quality_threshold)
    sample_cap = resolve_legacy_import_sample_cap()
    quality_rng = build_quality_rng()

    logger.info(f"Starting legacy import from {source_dir}")
    logger.info(f"Database: {db_path}")
    logger.info(f"Quality threshold: {quality_threshold}")
    logger.info(f"Quality sample cap: {sample_cap}")
    logger.info(f"Quality RNG seed: {resolve_legacy_import_rng_seed()}")

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
            await import_factoid_file(
                is_file,
                FactoidType.IS,
                store,
                quality_threshold=quality_threshold,
                stats=total_stats,
                sample_cap=sample_cap,
                rng=quality_rng,
            )

        if are_file and are_file.exists():
            await import_factoid_file(
                are_file,
                FactoidType.ARE,
                store,
                quality_threshold=quality_threshold,
                stats=total_stats,
                sample_cap=sample_cap,
                rng=quality_rng,
            )

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
        default=0.55,
        help="Minimum quality score to import (0.0-1.0, default: 0.55)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure module-scoped logging without polluting root logger.
    configure_import_logging(verbose=args.verbose)

    try:
        validate_quality_threshold(args.quality_threshold)
        resolve_legacy_import_sample_cap()
        resolve_legacy_import_rng_seed()
    except ValueError as e:
        parser.error(str(e))

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
    print()
    for line in render_import_summary(stats, args.quality_threshold):
        print(line)

    if stats.imported > 0:
        print(f"\n✓ Import complete! {stats.imported} factoids imported.")
    else:
        print("\n✗ No factoids were imported.")


if __name__ == "__main__":
    main()
