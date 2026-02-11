# Plan: Legacy Import Quality Score Observability

## Context

`src/infobot/tools/legacy_import.py` currently supports quality-threshold filtering,
but observability is weak during long-running imports:

- `--verbose` currently configures root logging, which can pull in noisy dependency
  logs and drown out import diagnostics.
- Low-quality entries only log score/key and do not provide enough context to tune
  `--quality-threshold` quickly.
- Progress diagnostics can become sparse when threshold is strict.
- Final summary lacks distribution shape and representative accepted/rejected examples.

For 50k+ row imports, threshold tuning becomes slow and error-prone.

## Goals

1. Keep verbose logging focused on import diagnostics only.
2. Provide periodic quality visibility during import runs.
3. Show representative accepted and rejected samples during the run so operators can
   abort and rerun with better parameters.
4. Provide comprehensive final score distribution and sample summary.
5. Preserve core import correctness (parsing, cleaning, dedupe, filtering).
6. Keep telemetry overhead bounded and testable.

## Non-Goals

1. Changing quality heuristics in `calculate_quality_score`.
2. Auto-adjusting threshold or adding adaptive threshold logic.
3. Adding persistence of quality telemetry to the database.
4. Implementing resume/checkpoint functionality.

## Success Metrics

1. Periodic diagnostics appear at least every 60 seconds while parsing is active.
2. Telemetry overhead remains <= 10% on a 100k-row synthetic run.
3. Telemetry memory overhead stays reasonable for the 50k-100k target range.
4. Summary generation remains fast on large inputs (target <= 3s on 100k scored rows).

## Design Decisions

1. Sampling
- Use reservoir sampling with bounded sample buffers.
- Keep accepted and rejected samples separately.

2. Sample sizes
- Default sample cap: 20 accepted and 20 rejected.
- Sample cap is configurable via `LEGACY_IMPORT_SAMPLE_CAP` (minimum 5).

3. Sampling reproducibility
- Production uses random sampling.
- Tests and reproducible debugging can set `LEGACY_IMPORT_RNG_SEED`.

4. Progress cadence
- Trigger periodic diagnostics using parsed-count and time fallback.
- Use monotonic time (`time.monotonic()`) for cadence checks.
- First report at `parsed >= 100` or 30 seconds.
- Subsequent reports at every +1000 parsed or 30 seconds, whichever comes first.
- Never emit more than one periodic report per loop iteration.

5. Bucket granularity
- Track score distribution in 10 buckets:
- `[0.0, 0.1)`, `[0.1, 0.2)`, `[0.2, 0.3)`, `[0.3, 0.4)`, `[0.4, 0.5)`,
  `[0.5, 0.6)`, `[0.6, 0.7)`, `[0.7, 0.8)`, `[0.8, 0.9)`, `[0.9, 1.0]`.
- Periodic logs use compact rendering; final summary includes full 10-bucket table.

6. Summary statistics
- Include min/avg/max plus `p50`, `p75`, `p90`, `p95`.
- Include threshold guidance with explicit guardrails for low sample counts.

## Implementation Plan

### 0) Input Validation and Runtime Semantics

In `main()` and import entry points:

- Validate `--quality-threshold` is within `[0.0, 1.0]`.
- Fatal setup failures (missing source dir, DB initialization failure) should produce
  non-zero exit behavior.
- Per-line parse/import failures remain non-fatal and are counted in `stats.errors`.

### 1) Logging Isolation and Idempotency

In `src/infobot/tools/legacy_import.py`:

- Replace root `logging.basicConfig(...)` usage with
  `configure_import_logging(verbose: bool)`.
- Configure only module logger `infobot.tools.legacy_import` with a dedicated
  `StreamHandler`.
- Set formatter explicitly.
- Set logger level from `--verbose`.
- Set `logger.propagate = False`.
- Make setup idempotent:
- remove/replace prior handler created by this function
- avoid duplicated handlers when called multiple times
- do not mutate root logger handlers/level

### 2) Extend Data Model for Quality Telemetry

In `src/infobot/tools/legacy_import.py`:

Add `QualitySample` dataclass:
- `key: str`
- `value: str`
- `score: float`
- `accepted: bool`
- `source_file: str`
- `line_num: int`

Extend `ImportStats` with:
- `quality_scores: list[float]`
- `quality_count: int`
- `quality_sum: float`
- `quality_min: float | None`
- `quality_max: float | None`
- `quality_p50: float | None`
- `quality_p75: float | None`
- `quality_p90: float | None`
- `quality_p95: float | None`
- `quality_buckets: list[int]` (length 10)
- `accepted_seen: int`
- `rejected_seen: int`
- `accepted_samples: list[QualitySample]`
- `rejected_samples: list[QualitySample]`
- `next_quality_report_at_parsed: int` (initial 100)
- `last_quality_report_ts: float | None` (monotonic timestamp)

### 3) Add Telemetry Helpers

Add private helpers in `src/infobot/tools/legacy_import.py`:

- `_quality_bucket_index(score: float) -> int`
- `_record_quality(stats: ImportStats, score: float) -> None`
- `_reservoir_add(..., rng: random.Random) -> int`
- `_quality_mean(stats: ImportStats) -> float | None`
- `_compute_quality_percentiles(scores: list[float]) -> dict[str, float | None]`
- `_quality_bucket_rows(stats: ImportStats) -> list[tuple[str, int, float]]`
- `_ascii_histogram(rows: list[tuple[str, int, float]]) -> str`
- `_sample_preview(samples: list[QualitySample], limit: int = 3) -> str`
- `_threshold_guidance(stats: ImportStats, threshold: float) -> str`

Helper constraints:
- deterministic under seeded RNG
- explicit zero-count handling
- clamp bucket index boundaries

### 4) Instrument `import_factoid_file(...)`

For each parsed candidate:

- Clean key/value.
- Compute quality score.
- Record score metrics and bucket counts.
- Build `QualitySample` and feed accepted/rejected reservoir based on threshold.
- Preserve current import behavior for DB writes, duplicates, and error counters.

Periodic reporting:

- Trigger when parsed or time condition is met.
- Include:
- parsed/imported/skipped_invalid/skipped_low_quality/duplicates/errors
- reject rate
- min/avg/max
- 10-bucket compact histogram
- up to 3 accepted and 3 rejected sample previews
- high reject-rate warning text when applicable

### 5) Global Telemetry Across IS and ARE Files

In `import_legacy_data(...)`:

- Initialize one shared `ImportStats` at start.
- Pass same stats object through IS and ARE import calls.
- Avoid merge-by-copy logic so cadence and totals remain monotonic and accurate.

### 6) Final Summary Upgrade

In CLI summary output:

- Keep current top-level counters.
- Add quality block:
- scored count
- min/avg/max/p50/p75/p90/p95
- full 10-bucket table with counts and percentages
- compact ASCII histogram
- accepted sample section (up to cap)
- rejected sample section (up to cap)
- threshold guidance section

Guidance rules:

- If `threshold > p90`, warn threshold is aggressive.
- If `threshold < p10`, note threshold is permissive.
- If reject rate > 70%, suggest lowering threshold or abort/rerun.
- If `quality_count < 200`, prefix guidance with low-confidence warning.
- If no accepted or no rejected examples, suppress directional guidance and explain why.

### 7) Configuration Additions

In `src/infobot/config.py`:

- Add `legacy_import_sample_cap` sourced from `LEGACY_IMPORT_SAMPLE_CAP` (default 20,
  validate >= 5).
- Add `legacy_import_rng_seed` sourced from `LEGACY_IMPORT_RNG_SEED` (optional int).

### 8) Documentation Update

Update `docs/legacy_import.md` with:

- verbose logging behavior and root-logger isolation
- periodic diagnostics cadence and sample previews
- 10-bucket histogram and percentile explanations
- threshold guidance interpretation
- new environment variables for sample cap and RNG seed

### 9) Test Plan (`tests/test_legacy_import.py`)

Add/expand tests:

1. bucket assignment boundaries (including score 1.0)
2. aggregate math and zero-count behavior
3. percentile math on controlled arrays
4. reservoir caps and replacement behavior
5. deterministic sampling with seeded RNG
6. periodic logs include histogram and sample previews
7. time-based fallback trigger path (with monotonic clock mocking)
8. no parsed-candidates edge case
9. logger root isolation
10. logger setup idempotency (no duplicate handlers)
11. cross-file aggregation with shared stats object
12. threshold guidance rule behavior, including low-confidence guardrail
13. threshold validation failure path

## Validation

1. `pytest tests/test_legacy_import.py -v`
2. optional smoke run on representative dataset with `--verbose`
3. verify output cadence, histogram clarity, and sample usefulness for threshold tuning

## Risks and Mitigations

1. Telemetry overhead could slow imports.
- Mitigation: O(1) per-row updates, bounded sample buffers, percentile sort at end only.

2. Progress logs could still be too noisy.
- Mitigation: parsed/time cadence and compact rendering.

3. Guidance could be misleading on small sample sizes.
- Mitigation: explicit low-confidence guardrail and edge-case suppression.

4. Cross-file aggregation bugs could skew distributions.
- Mitigation: single shared stats object and dedicated cross-file tests.

5. Very large future datasets could pressure score-list memory.
- Mitigation: guardrail documented; if needed, move to bounded-memory quantile strategy
  in follow-up feature.

## Acceptance Criteria

1. Verbose mode reports import diagnostics without dependency log flood.
2. Periodic diagnostics include representative accepted/rejected samples during run.
3. Periodic diagnostics include distribution/histogram signal sufficient for mid-run
   threshold decisions.
4. Final summary includes percentiles, 10-bucket distribution, samples, and guidance.
5. Existing import behavior remains correct.
6. `pytest tests/test_legacy_import.py -v` passes.

## Out of Scope After Planning

No implementation begins in this phase. After planning and bead finalization are
committed, work is delegated to worker agents.
