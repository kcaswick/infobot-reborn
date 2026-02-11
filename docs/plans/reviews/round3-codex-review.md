1. **Add explicit success metrics and budgets**
Rationale: Current acceptance criteria are qualitative. Adding measurable targets makes the plan testable and reduces ambiguity during implementation/review.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 ## Goals
@@
 5. Preserve import correctness (parsing, cleaning, dedupe, filtering behavior).
+6. Keep observability overhead bounded and measurable on large inputs.
+
+## Success Metrics
+
+1. Throughput impact from telemetry is <= 10% versus baseline import on a 100k-row fixture.
+2. Peak telemetry memory overhead is <= 25 MB at 100k scored rows.
+3. Periodic report cadence never exceeds 30 seconds between reports while parsing is active.
+4. Summary generation after import completes in <= 2 seconds for 100k scored rows.
```

2. **Replace unbounded `quality_scores` storage with streaming quantiles**
Rationale: Storing all scores is simple but can become memory-heavy and slower for larger imports; streaming quantiles + histogram keep memory bounded.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 Extend `ImportStats`:
 - Raw/aggregate quality telemetry
-  - `quality_scores: list[float]`
   - `quality_count: int`
   - `quality_sum: float`
   - `quality_min: float | None`
   - `quality_max: float | None`
 - Percentiles (computed for summary output)
-  - `quality_p50: float | None`
-  - `quality_p75: float | None`
-  - `quality_p90: float | None`
-  - `quality_p95: float | None`
+  - `quality_quantiles: OnlineQuantiles` (tracks p50/p75/p90/p95 incrementally)
@@
 Add internal helpers in `legacy_import.py`:
@@
-- `_compute_quality_percentiles(scores: list[float]) -> dict[str, float | None]`
+- `_update_quality_quantiles(stats: ImportStats, score: float) -> None`
+- `_quality_percentiles(stats: ImportStats) -> dict[str, float | None]`
@@
 Constraints:
 - Helpers should be deterministic for tests given a seeded RNG.
 - Clamp and division-by-zero behavior must be explicit.
+- Quantile implementation must be bounded-memory (no full-score list retention).
```

3. **Use monotonic clock and strict cadence semantics**
Rationale: Wall-clock drift can break time-based reporting; monotonic time makes cadence reliable.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 3. Progress cadence
 - Trigger periodic diagnostics by parsed-candidate counts with time fallback.
 - Report when either condition is met:
 - first report at parsed >= 100 or after 30 seconds
 - then every +1000 parsed or after 30 seconds since last report
+- Use `time.monotonic()` (not wall clock) for all cadence checks.
+- Never emit more than one periodic report per loop iteration.
```

4. **Harden logging setup to be idempotent and non-duplicative**
Rationale: Re-running `main()` (tests/in-process execution) can duplicate handlers and spam logs unless setup is idempotent.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 Changes:
 - Add `configure_import_logging(verbose: bool) -> logging.Logger`.
 - Configure only `infobot.tools.legacy_import` logger with a dedicated `StreamHandler`.
 - Set formatter explicitly.
 - Set logger level from verbose flag.
 - Set `logger.propagate = False`.
 - Avoid global `logging.basicConfig` in this module.
+- Make configuration idempotent:
+  - remove/replace prior handlers created by this function
+  - avoid duplicate handlers across repeated calls
+  - do not mutate root logger level/handlers
```

5. **Make threshold guidance statistically safer**
Rationale: Guidance can be misleading on tiny samples; add minimum sample size and confidence messaging.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 - Threshold guidance block
@@
 - explicit trigger rules:
 - if threshold > p90: warn that threshold is highly aggressive
 - if threshold < p10: note that threshold is very permissive
 - if reject rate > 70%: recommend lower threshold or abort and rerun
+- guidance guardrails:
+  - if `quality_count < 200`, print "low-confidence guidance (small sample)"
+  - if no rejected or no accepted samples observed, suppress directional advice and print why
```

6. **Strengthen input/runtime reliability requirements**
Rationale: Plan should explicitly cover validation and failure behavior for safer execution.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 ## Implementation Plan
+
+### 0) Input Validation and Exit Semantics
+
+Changes:
+- Validate `--quality-threshold` is in `[0.0, 1.0]`; fail fast with clear error otherwise.
+- Ensure fatal setup failures (missing source dir, DB init failure) produce non-zero process exit.
+- Keep per-line parse/import failures non-fatal and counted in `errors`.
```

7. **Expand test plan with performance and repeatability checks**
Rationale: Existing tests cover correctness but not overhead, cadence guarantees, or idempotent logger behavior under repeated runs.

```diff
diff --git a/docs/plans/legacy-import-quality-observability-plan.md b/docs/plans/legacy-import-quality-observability-plan.md
@@
 Add/expand tests for:
@@
 9. Logger setup behavior (module logger configured without root reconfiguration).
+10. Logger setup idempotency (multiple calls do not duplicate handlers).
+11. Cross-file aggregate monotonic reporting cadence (shared stats object across IS/ARE).
+12. Performance regression guard on synthetic dataset (telemetry overhead budget).
+13. Guidance guardrail behavior for low sample counts (`quality_count < 200`).
```

If you want, I can also provide a **single consolidated patch** combining all of the above so it can be applied directly to `docs/plans/legacy-import-quality-observability-plan.md`.
