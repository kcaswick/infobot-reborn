I've carefully analyzed all three competing reviews. Each brings valuable perspectives:

- **Sonnet** emphasizes practical operator experience with features like JSON output, dry-run mode, and diversity-aware sampling
- **Gemini** focuses on statistical rigor with 10-bucket histograms and explicit implementation patterns
- **Codex** prioritizes performance budgets, streaming algorithms, and hardening against edge cases

Let me provide a comprehensive git-diff that integrates the best ideas from all reviews into a superior hybrid plan:

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
index original..enhanced 100644
--- a/docs/plans/legacy-import-quality-observability-plan.md
+++ b/docs/plans/legacy-import-quality-observability-plan.md
@@ -14,7 +14,11 @@ For real datasets (50k+ records), this makes threshold tuning slow and error-pr
 
 ## Goals
 
-1. Keep verbose logging focused on import diagnostics only.
+1. Keep verbose logging focused on import diagnostics only, isolated from noisy
+   dependency logs.
 2. Provide periodic, compact quality visibility during import runs.
 3. Show representative accepted and rejected examples during the run so operators can
    abort and rerun with better parameters.
@@ -22,18 +26,30 @@ For real datasets (50k+ records), this makes threshold tuning slow and error-pr
 5. Preserve import correctness (parsing, cleaning, dedupe, filtering behavior).
+6. Keep observability overhead bounded and measurable on large inputs.
+7. Enable both interactive operator use and automated pipeline integration.
+
+## Success Metrics
+
+1. Throughput impact from telemetry is <= 10% versus baseline import on a 100k-row
+   fixture.
+2. Peak telemetry memory overhead is <= 30 MB at 100k scored rows.
+3. Periodic report cadence never exceeds 60 seconds between reports while parsing is
+   active.
+4. Summary generation after import completes in <= 3 seconds for 100k scored rows.
+5. Test suite execution time for telemetry tests is <= 5 seconds.
 
 ## Non-Goals
 
 1. Changing quality heuristics in `calculate_quality_score`.
 2. Auto-adjusting `--quality-threshold`.
-3. Adding new CLI output formats in this feature.
+3. Adding complex CLI configuration beyond `--output-json` and `--dry-run`.
 4. Storing quality telemetry in the database.
+5. Import resume/checkpoint capability (defer to separate feature).
+6. Sample diversity scoring (defer to follow-up if operator feedback indicates value).
 
 ## Design Decisions
 
 1. Sampling strategy
-- Use reservoir sampling with fixed-size buffers for accepted and rejected records.
+- Use reservoir sampling with configurable-size buffers for accepted and rejected records.
 - Keep memory bounded and ensure samples remain representative across file size.
+- Use deterministic seeded RNG for test reproducibility, true random for production.
 
@@ -41,19 +57,32 @@ For real datasets (50k+ records), this makes threshold tuning slow and error-pr
 - Show samples in periodic logs and in final summary.
 - Do not defer all samples to end of run.
 
 3. Progress cadence
 - Trigger periodic diagnostics by parsed-candidate counts with time fallback.
+- Use `time.monotonic()` (not wall clock) for all cadence checks.
 - Report when either condition is met:
-- first report at parsed >= 100 or after 30 seconds
-- then every +1000 parsed or after 30 seconds since last report
+  - first report at `parsed >= 100` OR after 30 seconds
+  - then every `+1000` parsed OR after 30 seconds since last report (whichever first)
+- Never emit more than one periodic report per loop iteration.
+- Guarantee operator sees progress within 60 seconds even if threshold is very strict.
 
 4. Bucket granularity
-- Track scores in 10 equal-width buckets:
+- Track scores in **10 equal-width buckets** for histogram precision:
 - `[0.0, 0.1)`, `[0.1, 0.2)`, `[0.2, 0.3)`, `[0.3, 0.4)`, `[0.4, 0.5)`,
   `[0.5, 0.6)`, `[0.6, 0.7)`, `[0.7, 0.8)`, `[0.8, 0.9)`, `[0.9, 1.0]`
-- For readability, periodic logs can show collapsed 4-bin rollups while final summary
-  shows all 10 buckets.
+- Rationale: 4-bin rollups are too coarse for fine-tuning thresholds between 0.35 and
+  0.45. Ten bins provide the distribution "shape" needed for actionable decisions.
+- Periodic logs show all 10 buckets with compact ASCII histogram for at-a-glance
+  visual feedback.
 
 5. Summary percentiles
 - Include `p50`, `p75`, `p90`, and `p95` in final summary to make threshold tuning
   more actionable than min/avg/max alone.
+- Essential for understanding distribution shape: if avg=0.45 but p90=0.72, most data
+  is high-quality with long tail of junk—suggests lower threshold. If avg=0.45 but
+  p90=0.50, data is uniformly mediocre—different tuning strategy.
 
 6. Sample caps
-- Keep up to `20` accepted samples and `20` rejected samples.
+- Keep up to `N` accepted samples and `N` rejected samples (default `N=20`).
+- Configurable via `LEGACY_IMPORT_SAMPLE_CAP` environment variable (validated >= 5).
+- Rationale: Small exploratory imports (1k records) may need fewer; large production
+  imports with diverse quality patterns benefit from 50-100 samples.
 - Show up to `3` per category in periodic logs; show full stored samples in final
   summary.
 
+7. Memory management
+- For datasets under 200k scored rows, store all scores in Python list for exact
+  percentile computation.
+- If future datasets exceed 200k scored rows, replace `quality_scores: list[float]`
+  with streaming quantile approximation (e.g., `array.array('f')` or t-digest) in a
+  follow-up feature.
+- Guardrail documented but not implemented in this phase—current approach handles
+  stated 50k+ use case with margin.
+
+8. Output modes
+- Default: human-readable text with periodic progress and final summary
+- `--output-json`: machine-readable JSON summary (silent import except errors)
+- `--dry-run`: parse and score all candidates, generate full report, skip DB writes
+- Rationale: enable automated pipelines, CI/CD quality gates, and zero-risk threshold
+  exploration
+
 ## Implementation Plan
 
+### 0) Input Validation and Exit Semantics
+
+Add validation in `main()`:
+
+Changes:
+- Validate `--quality-threshold` is in `[0.0, 1.0]`; fail fast with clear error message.
+- Ensure fatal setup failures (missing source dir, DB init failure) produce non-zero
+  process exit.
+- Keep per-line parse/import failures non-fatal and counted in `stats.errors`.
+
+Expected result:
+- Operators receive immediate, actionable feedback on configuration errors.
+- Exit codes enable shell scripting and CI/CD integration.
+
 ### 1) Logging Isolation in `legacy_import.py`
 
@@ -65,12 +94,21 @@ Changes:
 - Set formatter explicitly.
 - Set logger level from verbose flag.
 - Set `logger.propagate = False`.
 - Avoid global `logging.basicConfig` in this module.
+- Make configuration idempotent:
+  - Remove/replace prior handlers created by this function on repeated calls
+  - Avoid duplicate handlers across multiple `main()` executions (matters for tests)
+  - Do not mutate root logger level/handlers
 
 Expected result:
 - `--verbose` raises verbosity for import logs without flooding with third-party DEBUG
   logs.
+- Re-running import (tests, interactive use) does not spam duplicate log lines.
 
 ### 2) Expand Stats Data Model
 
@@ -80,20 +118,24 @@ New dataclass:
 - `QualitySample`
   - `key: str`
   - `value: str`
   - `score: float`
   - `accepted: bool`
   - `source_file: str`
   - `line_num: int`
 
 Extend `ImportStats`:
 - Raw/aggregate quality telemetry
   - `quality_scores: list[float]`
   - `quality_count: int`
   - `quality_sum: float`
   - `quality_min: float | None`
   - `quality_max: float | None`
 - Percentiles (computed for summary output)
   - `quality_p50: float | None`
   - `quality_p75: float | None`
   - `quality_p90: float | None`
   - `quality_p95: float | None`
 - Bucket counters
-  - `quality_buckets: list[int]` (length 10)
+  - `quality_buckets: list[int]` (length 10, indices 0-9 for 0.1-width bins)
 - Reservoir state
   - `accepted_seen: int`
   - `rejected_seen: int`
   - `accepted_samples: list[QualitySample]`
   - `rejected_samples: list[QualitySample]`
 - Progress/report state
   - `next_quality_report_at_parsed: int` (initial `100`)
-  - `last_quality_report_ts: float | None`
+  - `last_quality_report_ts: float | None` (monotonic time)
+
+Add configuration fields to `config.py`:
+- `LEGACY_IMPORT_SAMPLE_CAP: int` (default `20`, read from env, validated >= 5)
+- `LEGACY_IMPORT_RNG_SEED: int | None` (default `None`, read from env)
+  - When set: deterministic reservoir sampling for test reproducibility
+  - When unset: true random sampling for production
 
 ### 3) Add Reusable Telemetry Helpers
 
@@ -101,7 +143,8 @@ Add internal helpers in `legacy_import.py`:
 
 - `_quality_bucket(score: float) -> str`
+  - Map score to bucket label (e.g., "[0.3, 0.4)")
 - `_record_quality(stats: ImportStats, score: float) -> None`
+  - Update count, sum, min, max, append to scores list, increment bucket counter
 - `_reservoir_add(
     samples: list[QualitySample],
     sample: QualitySample,
     seen_count: int,
     cap: int,
     rng: random.Random,
   ) -> int`
+  - Standard reservoir sampling algorithm, return updated seen_count
 - `_quality_mean(stats: ImportStats) -> float | None`
+  - Safe division, return None if count is zero
 - `_compute_quality_percentiles(scores: list[float]) -> dict[str, float | None]`
+  - Sort scores, extract p50/p75/p90/p95, handle empty list gracefully
 - `_quality_bucket_rows(stats: ImportStats) -> list[tuple[str, int, float]]`
+  - Generate (bucket_label, count, percentage) tuples for all 10 buckets
 - `_ascii_histogram(rows: list[tuple[str, int, float]]) -> str`
+  - Render compact ASCII bar chart (e.g., `[###.....]`) with bucket labels
+  - Rationale: visual feedback for at-a-glance distribution understanding
 - `_sample_preview(samples: list[QualitySample], limit: int = 3) -> str`
+  - Format sample entries with truncated values (90-120 chars), show score/file/line
+- `_threshold_recommendation(
+    stats: ImportStats,
+    threshold: float | None,
+    reject_rate: float,
+  ) -> str`
+  - Generate actionable guidance text based on percentiles and reject rate
+  - Heuristics: warn if threshold > p90, note if < p10, suggest adjustment if reject
+    rate > 70% or < 5%
+  - Guardrail: if `quality_count < 200`, prefix with "Low-confidence guidance (small
+    sample):"
+  - Guardrail: if no accepted or no rejected samples, suppress directional advice and
+    explain why
 
 Constraints:
 - Helpers should be deterministic for tests given a seeded RNG.
 - Clamp and division-by-zero behavior must be explicit.
+- All helpers are pure functions (no hidden state mutation).
 
 ### 4) Instrument Import Loop
 
 In `import_factoid_file(...)`:
 
+- Initialize `rng` from `config.LEGACY_IMPORT_RNG_SEED` if set, else `random.Random()`.
 - For each parsed candidate:
   - Clean key/value.
   - Compute score.
   - Record score/bucket/min/max/mean aggregates.
   - Push candidate to accepted or rejected reservoir based on threshold outcome.
 - Keep existing counters and DB write behavior unchanged.
-- Trigger periodic report when parsed/time threshold is met.
+- If `--dry-run` flag is set, skip all `await db_conn.execute(...)` calls.
+- Trigger periodic report when `parsed >= next_quality_report_at_parsed` OR
+  `(monotonic_time - last_quality_report_ts) >= 30.0`.
+- On periodic report trigger:
+  - Emit log with: parsed/imported/skipped_invalid/skipped_low_quality/duplicates/errors
+  - Show reject rate, min/avg/max
+  - Show compact 10-bucket histogram with ASCII visualization
+  - Show accepted preview (up to 3) and rejected preview (up to 3)
+  - If reject rate > 50%, include hint: "High reject rate—review samples and consider
+    lowering threshold or abort with Ctrl-C"
+  - Update `next_quality_report_at_parsed += 1000`
+  - Update `last_quality_report_ts = time.monotonic()`
 
-Periodic report content:
-- Parsed/imported/skipped_invalid/skipped_low_quality/duplicates/errors
-- Reject rate (`skipped_low_quality / parsed`)
-- Min/avg/max
-- Bucket counts and percentages (4-bin collapsed rollup)
-- Compact ASCII histogram view of the four periodic bins
-- Accepted preview (up to 3)
-- Rejected preview (up to 3)
-- Hint line when reject rate is high (for threshold-tuning/abort decision)
-
 ### 5) Ensure Global Cross-File Telemetry
 
 `import_legacy_data(...)` processes both `*-is.txt` and `*-are.txt`.
 
-Requirement:
+Implementation:
-- Final telemetry must reflect both files combined.
+- Initialize **one** `ImportStats` instance in `import_legacy_data(...)`.
+- Pass the same instance into each `import_factoid_file(...)` call.
+- Do not merge stats objects—single shared instance ensures monotonic progress
+  cadence and accurate cross-file aggregation.
 
-Implementation approach:
-- Initialize one `ImportStats` instance in `import_legacy_data(...)`.
-- Pass the same instance into each `import_factoid_file(...)` call.
-- Avoid merge-by-copy logic for progress telemetry so parsed/time cadence stays
-  monotonic.
+Expected result:
+- Periodic reports and final summary reflect combined IS+ARE data.
+- No duplicate bucket counts or reservoir samples.
 
 ### 6) Final Summary Upgrade
 
-In CLI summary section (`main()`), keep current lines and append:
+In CLI summary section (`main()`):
+
+If `--output-json` flag is set:
+- Serialize `ImportStats` to JSON (include all fields: counters, buckets, percentiles,
+  samples).
+- Print JSON to stdout.
+- Do not print periodic logs (silent import except errors).
+- Rationale: enable automated quality monitoring, CI/CD integration, scripted threshold
+  tuning.
+
+Else (default text mode):
+- Keep current summary lines (total records, imported, skipped, errors, timing).
+- Append quality telemetry block:
 
 - Quality score overview
   - scored entries
   - min/avg/max/p50/p75/p90/p95
-- Histogram block
-  - each 0.1 bucket with count + percentage
-  - compact ASCII bar chart for the 10 buckets
+  - Rationale: percentiles are essential for understanding distribution shape and
+    tuning thresholds effectively
+
+- Histogram block (10 buckets)
+  - Table format: `[0.X, 0.Y): count (percentage)`
+  - Compact ASCII bar chart for visual distribution view
+  - Example:
+    ```
+    [0.0, 0.1):    5 (  0.5%)  [▁       ]
+    [0.1, 0.2):   12 (  1.2%)  [▂       ]
+    [0.2, 0.3):   45 (  4.5%)  [▃▃      ]
+    [0.3, 0.4):  150 ( 15.0%)  [█████   ]
+    [0.4, 0.5):  320 ( 32.0%)  [██████████]
+    [0.5, 0.6):  280 ( 28.0%)  [████████  ]
+    [0.6, 0.7):  140 ( 14.0%)  [█████     ]
+    [0.7, 0.8):   35 (  3.5%)  [▃        ]
+    [0.8, 0.9):    8 (  0.8%)  [▁        ]
+    [0.9, 1.0]:    5 (  0.5%)  [▁        ]
+    ```
+
 - Samples block
   - accepted samples (up to 20)
+    - format: `score=0.XX | key | value (truncated to 120 chars) | file:line`
   - rejected samples (up to 20)
+    - same format
 - Threshold guidance block
-  - summarize current threshold behavior from reject rate + percentiles
-  - include practical recommendation text (for example lower, hold, or raise threshold)
-  - explicit trigger rules:
-  - if threshold > p90: warn that threshold is highly aggressive
-  - if threshold < p10: note that threshold is very permissive
-  - if reject rate > 70%: recommend lower threshold or abort and rerun
+  - If `--quality-threshold` was specified:
+    - Analyze current threshold effectiveness using percentiles and reject rate
+    - Provide specific recommendation with rationale
+    - Example: "Current threshold 0.5 accepted 78% of data (p50=0.48, p75=0.62).
+      Consider threshold 0.35 to capture more of the p25-p50 range."
+    - Trigger rules:
+      - If `threshold > p90`: "⚠️  Threshold is very aggressive—discarding >90% of data.
+        Review rejected samples carefully."
+      - If `threshold < p10`: "ℹ️  Threshold is very permissive—accepting >90% of data.
+        Quality filtering may be ineffective."
+      - If reject rate > 70%: "⚠️  High reject rate. Review samples and consider
+        lowering threshold or aborting to preserve time."
+      - If reject rate < 5%: "ℹ️  Low reject rate. Threshold may be too permissive for
+        effective quality control."
+    - Guardrails:
+      - If `quality_count < 200`: prefix all guidance with "⚠️  Low-confidence guidance
+        (small sample, n=XXX):"
+      - If no rejected samples: "Cannot provide reject-side guidance—no data below
+        threshold."
+      - If no accepted samples: "Cannot provide accept-side guidance—no data above
+        threshold."
 - Truncate value previews to readable width (for example 90-120 chars).
 
+If `--dry-run` flag was set:
+- Add prominent banner: `*** DRY RUN MODE — NO DATA WRITTEN TO DATABASE ***`
+
 ### 7) Documentation Update
 
 Update `docs/legacy_import.md`:
 
 - Describe verbose logging scope and no-root-pollution behavior.
 - Document periodic quality reports and cadence.
-- Document histogram buckets and percentile summary.
+- Document 10-bucket histogram and percentile summary.
 - Document accepted/rejected sampling and that samples are representative.
+- Document `--output-json` for automation and `--dry-run` for threshold exploration.
+- Document environment variables: `LEGACY_IMPORT_SAMPLE_CAP`, `LEGACY_IMPORT_RNG_SEED`.
+- Provide example workflows:
+  - Interactive threshold tuning with `--dry-run` and `--verbose`
+  - Automated quality monitoring with `--output-json`
+  - CI/CD quality gate integration
+
+### 8) Add CLI Flags
+
+In `main()` argument parser:
+
+Add flags:
+- `--output-json`: Output final summary as JSON to stdout (suppresses periodic logs,
+  silent except errors)
+- `--dry-run`: Parse and score all candidates, generate full quality report, skip all
+  database writes
+
+Expected behavior:
+- `--output-json` enables machine-readable output for automation
+- `--dry-run` enables zero-risk threshold exploration
+- Flags can be combined: `--dry-run --output-json` for automated pre-import validation
 
-### 8) Test Plan (`tests/test_legacy_import.py`)
+### 9) Test Plan (`tests/test_legacy_import.py`)
 
 Add/expand tests for:
 
 1. Bucket assignment at boundaries (`0.3`, `0.5`, `0.7`, `1.0`).
+   - Verify edge case: score=1.0 goes to `[0.9, 1.0]` bucket, not out-of-bounds
 2. Aggregate math (`quality_count`, `quality_sum`, mean, min, max).
+   - Test zero-count edge case (mean returns None)
 3. Percentile math for known score arrays.
+   - Test edge cases: empty list, single element, odd/even length lists
 4. Reservoir cap enforcement (never exceed 20 per group).
+   - Test with `LEGACY_IMPORT_SAMPLE_CAP` override
 5. Deterministic sampling with injected seeded RNG.
+   - Set `LEGACY_IMPORT_RNG_SEED=42`, verify identical samples across runs
 6. Periodic logging presence and content (including sample previews and histogram) via
    `caplog`.
+   - Verify first report at parsed=100
+   - Verify subsequent reports every 1000 parsed
 7. Time-based fallback reporting path.
+   - Mock `time.monotonic()` to force time-based trigger even when parsed < 1000
 8. No parsed candidates edge case (safe summary output, no divide-by-zero).
 9. Logger setup behavior (module logger configured without root reconfiguration).
+10. Logger setup idempotency (multiple calls do not duplicate handlers).
+    - Call `configure_import_logging()` twice, verify single handler
+11. Cross-file aggregate monotonic reporting cadence (shared stats object across
+    IS/ARE).
+    - Verify `next_quality_report_at_parsed` increments correctly
+12. Threshold recommendation logic for various percentile/reject-rate combinations.
+    - High threshold (> p90): expect aggressive warning
+    - Low threshold (< p10): expect permissive note
+    - Small sample (< 200): expect low-confidence prefix
+13. `--dry-run` flag: verify no DB writes occur, full telemetry is generated.
+14. `--output-json` flag: verify valid JSON output, suppressed periodic logs.
+15. Performance regression guard on synthetic dataset (telemetry overhead budget).
+    - Generate 100k synthetic factoids
+    - Measure import time with and without telemetry
+    - Assert telemetry overhead <= 10%
+    - Assert peak memory increase <= 30 MB
+16. Input validation: invalid `--quality-threshold` values rejected with clear error.
 
 ## Validation
 
 1. Run focused tests:
 - `pytest tests/test_legacy_import.py -v`
+- `pytest tests/test_legacy_import.py -v --cov=src.infobot.tools.legacy_import
+  --cov-report=term-missing`
 
 2. Optional manual smoke run:
 - `python -m infobot.tools --source <legacy_dir> --quality-threshold 0.3 --verbose`
+- `python -m infobot.tools --source <legacy_dir> --quality-threshold 0.5 --dry-run
+  --verbose`
+- `python -m infobot.tools --source <legacy_dir> --quality-threshold 0.7
+  --output-json > quality_report.json`
 
 3. Verify manual output properties:
 - Periodic diagnostics at expected parsed/time thresholds.
+- Periodic diagnostics include 10-bucket histogram with ASCII visualization.
 - Sample previews show both accepted and rejected records during run.
-- Final summary contains histogram, percentiles, and sample sections.
+- Final summary contains 10-bucket histogram, percentiles, samples, and threshold
+  guidance.
+- Threshold guidance includes specific recommendations with rationale.
+- `--dry-run` shows banner and skips DB writes.
+- `--output-json` produces valid JSON with all telemetry fields.
+
+4. Performance validation:
+- Run on 100k synthetic factoid fixture
+- Verify throughput degradation <= 10%
+- Verify memory overhead <= 30 MB
+- Verify summary generation <= 3 seconds
 
 ## Risks and Mitigations
 
 1. Risk: Additional telemetry slows import noticeably.
 - Mitigation: O(1) operations per parsed row, bounded sample memory, percentile
   sorting only at summary time.
-- Additional guardrail: if future datasets exceed 1M scored rows, switch
-  `quality_scores` storage from Python list to a lower-memory strategy (for example
-  `array('f')` or streaming quantile approximation) in a follow-up feature.
+- Performance budget: <= 10% overhead on 100k-row import (validated by tests).
+- Additional guardrail: if future datasets exceed 200k scored rows, switch
+  `quality_scores` to streaming quantile approximation (`array.array('f')` or t-digest)
+  in a follow-up feature.
 
 2. Risk: Progress logs become too noisy.
 - Mitigation: parsed/time cadence and compact rendering format.
+- Further mitigation: `--output-json` suppresses all periodic logs for automated use.
 
 3. Risk: Sample text contains problematic characters.
 - Mitigation: reuse cleaned strings and truncate preview output.
+- Additional mitigation: escape control characters in preview rendering.
 
 4. Risk: Cross-file aggregation introduces mistakes.
-- Mitigation: dedicated aggregation helper plus tests for combined IS/ARE runs.
+- Mitigation: single shared `ImportStats` instance (no merge logic) plus tests for
+  combined IS/ARE runs.
 
 5. Risk: Threshold guidance could overfit noisy distributions.
 - Mitigation: keep guidance heuristic and conservative, and always include sample
   evidence.
+- Additional mitigation: low-confidence warnings for small samples (< 200 scored rows).
+- Additional mitigation: suppress directional advice when no rejected or no accepted
+  samples exist.
+
+6. Risk: Percentile computation on 100k records may cause memory spike.
+- Mitigation: For stated 50k+ use case, 100k floats = 800 KB, acceptable. Sorting is
+  O(n log n) but only at summary time (once per import).
+- Guardrail: if future datasets exceed 200k scored rows, switch to streaming quantile
+  approximation in follow-up feature.
+
+7. Risk: Time-based periodic reports may fire too frequently if parsing is very fast.
+- Mitigation: use `max(time_delta >= 30, parsed_delta >= 1000)` logic to ensure at
+  least one condition is substantially met before triggering.
+- Additional constraint: never emit more than one periodic report per loop iteration.
+
+8. Risk: JSON output mode may expose internal structure and create unintended API
+   contract.
+- Mitigation: clearly document JSON schema as "unstable, for automation only" in CLI
+  help text and documentation.
+- If stabilization is needed later, use semantic versioning for schema changes.
+
+9. Risk: Logger setup may not be idempotent, causing duplicate handlers in tests.
+- Mitigation: explicitly remove/replace prior handlers in `configure_import_logging()`
+  before adding new handler.
+- Validation: test case verifies single handler after multiple setup calls.
+
+10. Risk: Dry-run mode may diverge from real import behavior over time.
+- Mitigation: minimize conditional logic—only DB writes are skipped, all other logic
+  (parsing, scoring, telemetry) is identical.
+- Validation: test case verifies dry-run produces identical telemetry to real import
+  (except for DB write counters).
 
 ## Acceptance Criteria
 
 1. Verbose import logs are actionable and not dominated by dependency debug noise.
 2. Periodic diagnostics include score stats, bucket distribution, compact histogram, and
    accepted/rejected sample previews.
-3. Final summary includes min/avg/max, percentiles, histogram counts/percentages, sample
-   sections, and threshold guidance.
+3. Periodic diagnostics appear at least every 60 seconds while parsing is active.
+4. Final summary includes min/avg/max, percentiles (p50/p75/p90/p95), 10-bucket
+   histogram with counts/percentages/ASCII visualization, sample sections (up to 20
+   each), and threshold guidance with specific recommendations.
+5. Threshold guidance includes actionable recommendations based on percentiles and
+   reject rate, with guardrails for small samples and edge cases.
-4. Existing core import behavior remains unchanged.
-5. `pytest tests/test_legacy_import.py -v` passes.
+6. `--output-json` produces valid JSON summary with all telemetry fields.
+7. `--dry-run` generates full telemetry without writing to database.
+8. Existing core import behavior remains unchanged (parsing, cleaning, deduplication,
+   filtering).
+9. `pytest tests/test_legacy_import.py -v` passes with >= 80% coverage.
+10. Performance overhead is <= 10% on 100k-row synthetic import.
+11. Memory overhead is <= 30 MB on 100k-row synthetic import.
+12. Logger setup is idempotent (no duplicate handlers on repeated calls).
+13. Documentation includes usage examples for interactive tuning, automation, and CI/CD
+    integration.
+
+## Future Considerations (Out of Scope)
+
+These features are explicitly deferred but architecturally supported:
+
+1. **Quality score storage in database**
+   - Use case: post-import pruning, quality-aware search ranking, decay/refresh
+     strategies
+   - Implementation: add `quality_score REAL` column to factoids table
+   - Status: defer until operator feedback indicates value
+
+2. **Import resume/checkpoint capability**
+   - Use case: fault tolerance for very large imports (100k+ records, 10-20 minutes)
+   - Implementation: serialize `ImportStats` every 5k records, resume from checkpoint on
+     restart
+   - Status: defer to separate feature bead
+   - Architecture note: `ImportStats` is designed to be serializable (simple types,
+     dataclass) to make future checkpoint support a clean addition
+
+3. **Sample diversity scoring**
+   - Use case: bias reservoir sampling toward diverse samples (avoid 16/20 samples
+     being "foo is bar" variants)
+   - Implementation: weighted probability in `_reservoir_add` favoring different score
+     buckets, key lengths, prefixes
+   - Status: defer to follow-up if operator feedback indicates value
+   - Rationale: adds complexity to sampling logic, diagnostic value gain unclear until
+     real-world usage
+
+4. **Streaming quantile approximation**
+   - Use case: memory-bounded percentile computation for datasets > 200k scored rows
+   - Implementation: replace `quality_scores: list[float]` with t-digest or similar
+   - Status: defer until datasets exceed current guardrail threshold
+   - Rationale: current approach handles stated 50k+ use case with margin; premature
+     optimization adds complexity
 
 ## Out of Scope After Planning
 
 No implementation begins in this phase. Implementation starts only after plan and beads
 are finalized and delegated.
```

## Summary of Integrated Enhancements

This hybrid plan combines the best insights from all three reviews:

### From Sonnet (Operator Experience)
- ✅ **JSON output mode** for automation/CI/CD integration
- ✅ **Dry-run mode** for zero-risk threshold exploration
- ✅ **Threshold recommendations** with specific, actionable guidance
- ✅ **Configurable sample cap** via environment variable
- ✅ **Deterministic RNG seed** for test reproducibility
- ✅ **ASCII histogram in periodic reports** for visual feedback
- ⚠️ **Sample diversity scoring** documented as future consideration (complexity trade-off)

### From Gemini (Statistical Rigor)
- ✅ **10-bucket histograms** (not 4) for fine-grained distribution visibility
- ✅ **Single shared ImportStats** across files (no merge logic) for monotonic progress
- ✅ **Explicit memory guardrail** for datasets > 200k rows
- ✅ **Specific threshold guidance triggers** (> p90 = aggressive, < p10 = permissive)

### From Codex (Performance & Hardening)
- ✅ **Explicit success metrics** (10% overhead, 30 MB memory, 60s cadence, 3s summary)
- ✅ **Monotonic time** for reliable cadence (not wall clock)
- ✅ **Idempotent logger setup** to prevent duplicate handlers
- ✅ **Input validation** with fail-fast behavior
- ✅ **Low-confidence warnings** for small samples (< 200 rows)
- ✅ **Performance regression tests** in test plan
- ⚠️ **Streaming quantiles** documented as future optimization (current approach sufficient for 50k-100k use case)

### Additional Synthesis
- **Future Considerations section** to document deferred features with architectural notes
- **Comprehensive test plan** covering correctness, performance, edge cases, and idempotency
- **Usage examples** in documentation for interactive, automated, and CI/CD workflows
- **Clear risk mitigations** for each identified concern with measurable constraints

The result is a **production-ready plan** that balances:
- **Operator usability** (visual feedback, recommendations, dry-run)
- **Automation readiness** (JSON output, exit codes, scriptability)
- **Performance discipline** (bounded memory, overhead budgets, streaming-ready architecture)
- **Statistical rigor** (10 buckets, percentiles, confidence guardrails)
- **Maintainability** (idempotent setup, comprehensive tests, clear future path)

This plan is now ready for bead creation and agent delegation.
