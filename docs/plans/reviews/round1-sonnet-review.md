I'll provide a comprehensive analysis of this plan with proposed improvements. Let me examine the architecture, design decisions, and implementation strategy.

## Proposed Revisions and Analysis

### 1. **Add Quality Score Histogram to Periodic Reports**

**Change:**
```diff
 Periodic report content:
 - Parsed/imported/skipped_invalid/skipped_low_quality/duplicates/errors
 - Reject rate (`skipped_low_quality / parsed`)
 - Min/avg/max
 - Bucket counts and percentages
+- ASCII histogram visualization (compact, single-line or 3-4 lines max)
 - Accepted preview (up to 3)
 - Rejected preview (up to 3)
 - Hint line when reject rate is high (for threshold-tuning/abort decision)
```

**Rationale:**
During a 50k+ record import, operators need at-a-glance visual feedback about score distribution without parsing tables. A compact ASCII histogram (e.g., `[▁▃▅█]` or `[###.......]`) immediately shows whether scores cluster at boundaries, are uniformly distributed, or heavily skewed. This enables faster threshold tuning decisions mid-run. Implementation cost is minimal (10-15 lines) but diagnostic value is high for interactive use.

---

### 2. **Add Configurable Sample Cap via Environment Variable**

**Change:**
```diff
 5. Sample caps
-- Keep up to `20` accepted samples and `20` rejected samples.
+- Keep up to `N` accepted samples and `N` rejected samples (default `N=20`).
+- Configurable via `LEGACY_IMPORT_SAMPLE_CAP` environment variable.
 - Show up to `3` per category in periodic logs, full stored samples in final summary.
```

```diff
+In `config.py`:
+- Add `LEGACY_IMPORT_SAMPLE_CAP: int = 20` (read from env, validated >= 5)
```

**Rationale:**
Different operators have different needs. During exploratory tuning on small datasets (1k records), 20 samples may be excessive. For production imports with diverse quality patterns, 50-100 samples provide better coverage. Making this configurable without adding CLI flags reduces interface complexity while providing power-user flexibility. Environment variables are already the project's configuration pattern (see `LLM_BASE_URL`, `DATABASE_PATH`). Validation ensures minimum usability threshold.

---

### 3. **Add Quality Score Percentiles (p50, p75, p90, p95)**

**Change:**
```diff
 Extend `ImportStats`:
 - Raw/aggregate quality telemetry
   - `quality_scores: list[float]`
   - `quality_count: int`
   - `quality_sum: float`
   - `quality_min: float | None`
   - `quality_max: float | None`
+  - `quality_p50: float | None`
+  - `quality_p75: float | None`
+  - `quality_p90: float | None`
+  - `quality_p95: float | None`
```

```diff
 Add internal helpers:
+- `_compute_percentiles(scores: list[float]) -> dict[str, float | None]`
```

```diff
 In CLI summary section:
 - Quality score overview
   - scored entries
-  - min/avg/max
+  - min/avg/max/p50/p75/p90/p95
```

**Rationale:**
Min/avg/max are insufficient for understanding distribution shape. If avg=0.45 but p90=0.72, most data is high-quality with a long tail of junk—operators should use a lower threshold. If avg=0.45 but p90=0.50, the data is uniformly mediocre—different tuning strategy needed. Percentiles are standard observability metrics for latency/quality distributions. Computing them is O(n log n) once at summary time (acceptable for 50k records), and they provide actionable tuning guidance that mean/median cannot. Storage cost: 4 floats. Diagnostic value: high.

---

### 4. **Add Threshold Recommendation in Final Summary**

**Change:**
```diff
 ### 6) Final Summary Upgrade
 
 In CLI summary section (`main()`), keep current lines and append:
 
 - Quality score overview
   - scored entries
   - min/avg/max
 - Histogram block
   - each bucket with count + percentage
 - Samples block
   - accepted samples (up to 20)
   - rejected samples (up to 20)
 - Truncate value previews to readable width (for example 90-120 chars).
+- Threshold recommendation section
+  - If `quality_threshold` was specified: suggest adjusted value based on percentiles/reject rate
+  - Example: "Current threshold 0.5 accepted 78% of data. Consider 0.35 to capture p25-p50 range."
+  - If reject rate > 50%: "High reject rate—review samples and consider lowering threshold"
+  - If reject rate < 5%: "Low reject rate—threshold may be too permissive for quality control"
```

**Rationale:**
Operators using `--quality-threshold` for the first time lack intuition about appropriate values. The plan correctly identifies threshold tuning as the core problem, but doesn't close the loop—it shows diagnostics but forces operators to interpret them manually. Adding automated recommendations (based on percentiles, reject rate, and bucket distribution) reduces iteration cycles from 3-4 runs to 1-2. This is a "pit of success" design: the tool actively guides operators toward good outcomes. Implementation: 30-40 lines of heuristic logic, fully testable, high value-add for the 50k+ record use case that motivated this work.

---

### 5. **Decouple Periodic Report Cadence from Parsed Count**

**Change:**
```diff
 3. Progress cadence
-- Trigger periodic diagnostics by parsed-candidate counts.
-- Report at first `parsed == 100`, then every `1000` parsed candidates.
+- Trigger periodic diagnostics by time intervals (30-60 seconds) OR parsed-count thresholds, whichever comes first.
+- First report at `parsed == 100` OR 30 seconds, then every `1000` parsed OR 60 seconds.
```

```diff
 Extend `ImportStats`:
+- `last_report_time: float | None` (wall-clock time of last periodic report)
```

```diff
 In `import_factoid_file(...)`:
 - Trigger periodic report when `stats.parsed >= stats.next_quality_report_at_parsed`.
+- Trigger periodic report when `stats.parsed >= stats.next_quality_report_at_parsed` OR `(time.time() - stats.last_report_time) >= 60`.
```

**Rationale:**
Current design has a subtle flaw: if `--quality-threshold` is very strict (e.g., 0.8), the import may parse 10k records but only accept 50, making progress diagnostics invisible for minutes. The plan acknowledges this ("progress diagnostics may lag or disappear") but doesn't fix it. Time-based fallback ensures operators always see activity within 60 seconds, preventing "is it hung?" confusion. This is standard practice for long-running CLI tools (rsync, cargo, npm). Implementation cost is trivial (store timestamp, check delta). Robustness gain is significant for edge-case threshold values.

---

### 6. **Add JSON Output Mode for Automation/Scripting**

**Change:**
```diff
 ## Non-Goals
 
 1. Changing quality heuristics in `calculate_quality_score`.
 2. Auto-adjusting `--quality-threshold`.
-3. Adding new CLI flags unless implementation pressure proves they are required.
+3. Adding new CLI flags unless implementation pressure proves they are required (exception: `--output-json` for automation).
 4. Storing quality telemetry in the database.
```

```diff
 Add CLI flag:
+- `--output-json`: Output final summary as JSON to stdout (no periodic logs, silent import except errors)
```

```diff
 Final summary section:
+- If `--output-json`: serialize `ImportStats` (including samples, buckets, percentiles) to JSON and print
+- Else: render human-readable text summary (current design)
```

**Rationale:**
The plan focuses on interactive operator use, but legacy imports often run in automated pipelines (cron jobs, CI/CD, batch processing). Text logs are hard to parse programmatically. Adding `--output-json` enables:
- Automated quality monitoring across multiple import runs
- Integration with observability dashboards (Grafana, Datadog)
- Scripted threshold tuning (bisection search on reject rate)
- Regression testing of quality score distributions

This aligns with project philosophy: "provide tooling for multi-agent workflows." JSON output makes the tool composable with other automation. Implementation: ~50 lines (dataclass JSON serialization + flag handling). Marginal cost, high leverage for production use.

---

### 7. **Add Deterministic RNG Seed for Testing**

**Change:**
```diff
 In `import_factoid_file(...)`:
 
 - For each parsed candidate:
   - Clean key/value.
   - Compute score.
   - Record score/bucket/min/max/mean aggregates.
-  - Push candidate to accepted or rejected reservoir based on threshold outcome.
+  - Push candidate to accepted or rejected reservoir based on threshold outcome (using RNG seeded from `LEGACY_IMPORT_RNG_SEED` env var if set, else random).
```

```diff
 In `config.py`:
+- Add `LEGACY_IMPORT_RNG_SEED: int | None = None` (read from env, validated)
```

**Rationale:**
Current plan specifies "Deterministic sampling with injected seeded RNG" in test plan but doesn't specify how to inject it. The most maintainable approach is environment variable control (matches project patterns) rather than test-only constructor parameters. This enables:
- Reproducible test runs (critical for CI)
- Reproducible production runs when debugging specific imports
- Easier manual verification of sampling behavior

Without this, reservoir sampling tests are flaky or require complex mocking. With this, tests set `LEGACY_IMPORT_RNG_SEED=42` and get deterministic samples. Production never sets it and gets randomness. Clean separation of concerns.

---

### 8. **Add Sample Diversity Scoring to Reservoir Selection**

**Change:**
```diff
 - `_reservoir_add(
     samples: list[QualitySample],
     sample: QualitySample,
     seen_count: int,
     cap: int,
     rng: random.Random,
+    diversity_weight: float = 0.3,
   ) -> int`
```

**Rationale:**
Standard reservoir sampling gives uniform probability to all elements, but for diagnostic purposes, diverse samples are more useful than redundant ones. Consider a dataset where 80% of rejected records are "foo is bar" with tiny variations—uniform sampling gives 16/20 samples of similar junk. Better: bias selection toward samples with diverse scores, key lengths, value lengths, or prefixes.

Algorithm: When deciding whether to replace an existing sample, apply a weighted probability that favors candidates with different characteristics (e.g., score bucket, key length decile). This is a minor tweak to `_reservoir_add` (~15 lines) that dramatically improves sample representativeness. Trade-off: slightly more complex logic, but tests ensure correctness, and the diagnostic value gain is substantial for real-world messy datasets.

**Alternative:** If implementation complexity is deemed too high during execution phase, defer to a follow-up bead. Include as optional enhancement rather than requirement.

---

### 9. **Add Dry-Run Mode**

**Change:**
```diff
 Add CLI flag:
+- `--dry-run`: Parse and score all candidates, generate full quality report, but skip database writes
```

**Rationale:**
Operators often need to evaluate quality distribution before committing to an import (which may take minutes and modify production DB). Current design requires running import, then manually rolling back if threshold was wrong—inefficient and risky. Dry-run mode enables:
- Zero-risk threshold exploration
- Quality distribution analysis before committing storage/time
- CI/CD validation of data quality without side effects

Implementation: trivial—skip `await db_conn.execute(...)` calls when flag is set, everything else runs normally. This is a standard pattern in Unix tools (git, rsync, apt) and scripting best practice. Cost: 5-10 lines. Value: significant reduction in tuning friction.

---

### 10. **Store Quality Metadata in Comments/Attrs (Optional)**

**Change:**
```diff
 ## Non-Goals
 
 1. Changing quality heuristics in `calculate_quality_score`.
 2. Auto-adjusting `--quality-threshold`.
 3. Adding new CLI flags unless implementation pressure proves they are required.
-4. Storing quality telemetry in the database.
+4. Storing quality telemetry in the database (reconsider if operator feedback indicates value).
```

**Discussion (Not Implemented Yet):**

The plan explicitly excludes storing quality scores in the database. This is reasonable for initial implementation, but consider future use cases:

- **Post-import pruning:** "Delete all factoids with score < 0.4" without re-parsing source files
- **Quality-aware search ranking:** Boost high-quality factoids in results
- **Decay/refresh strategies:** Periodically review low-quality entries for deletion
- **Audit trails:** "Which factoids were imported despite low scores?"

**Recommendation:** Keep as non-goal for THIS plan (scope control), but document as a "Future Considerations" section. If operators request these features post-launch, add a `quality_score REAL` column to factoids table in a follow-up bead. This preserves architectural option value without inflating current scope.

---

### 11. **Add Import Resume Capability (Future-Proof Architecture)**

**Change:**
```diff
 Extend `ImportStats`:
+- `source_file_checkpoint: str | None` (for multi-file resume)
+- `line_checkpoint: int` (for single-file resume)
```

```diff
 Add internal helpers:
+- `_save_checkpoint(stats: ImportStats, checkpoint_path: Path) -> None`
+- `_load_checkpoint(checkpoint_path: Path) -> ImportStats | None`
```

**Discussion (Not Implemented Yet):**

For 50k+ record imports that may take 10-20 minutes, crashes/interruptions lose all progress. Adding checkpoint/resume (save state every 5k records) enables:
- Fault tolerance for large imports
- Pause/resume workflows
- Incremental imports (resume after source file updates)

**Recommendation:** Do NOT implement in this bead—scope creep risk is high. Instead, architect `ImportStats` to be **serializable** (use `@dataclass` with simple types, avoid lambdas/generators). This makes future checkpoint support a clean addition (new bead, minimal refactoring) rather than a rewrite. Document this architectural decision in comments.

---

## Summary of Priority Recommendations

**Must-Have (High Value, Low Cost):**
1. ✅ **Add percentiles (p50, p75, p90, p95)** — Essential for distribution understanding
2. ✅ **Add time-based periodic report fallback** — Fixes strict-threshold invisibility bug
3. ✅ **Add deterministic RNG seed for tests** — Enables reliable testing
4. ✅ **Add dry-run mode** — Standard tool pattern, minimal cost
5. ✅ **Add threshold recommendation** — Closes the tuning loop

**Should-Have (High Value, Moderate Cost):**
6. ✅ **Add ASCII histogram to periodic reports** — Visual feedback is powerful
7. ✅ **Add configurable sample cap** — Power-user flexibility
8. ✅ **Add JSON output mode** — Automation/scripting enablement

**Could-Have (Nice-to-Have, Defer if Timeline Pressure):**
9. ⚠️ **Add sample diversity scoring** — Complex, defer to follow-up bead if needed
10. 📋 **Document quality score storage as future consideration** — Architecture note only

**Out-of-Scope (Explicitly Defer):**
11. ❌ **Import resume capability** — Large feature, separate bead

---

## Revised Risk Analysis

**New Risk:** Percentile computation on 50k records may cause memory spike.
- **Mitigation:** Use streaming percentile approximation (t-digest) OR compute only at summary time when list is already in memory. For 50k floats (400KB), exact percentiles are acceptable.

**New Risk:** Time-based periodic reports may fire too frequently if parsing is very fast.
- **Mitigation:** Use `max(time_delta >= 60, parsed_delta >= 1000)` logic with jitter to prevent log spam.

**New Risk:** JSON output mode may expose internal structure and create API contract.
- **Mitigation:** Clearly document JSON schema as "unstable, for automation only" in help text. Use semantic versioning if stabilization is needed later.

---

This analysis maintains the plan's core strengths (focused scope, strong testing, clear goals) while adding targeted improvements that multiply diagnostic value without significant complexity cost. The recommendations prioritize operator experience and tool composability—aligning with the project's multi-agent workflow philosophy.
