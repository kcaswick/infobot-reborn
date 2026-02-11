The proposed plan is solid and addresses the core observability gaps. To make it more robust and useful for high-volume tuning, I recommend the following refinements:

1.  **Histogram Granularity:** Increase bucket granularity from 4 to 10 (0.1 increments). Four buckets are too coarse for fine-tuning a threshold between, for example, 0.35 and 0.45.
2.  **Stateless aggregation:** Instead of a `merge_import_stats` helper, explicitly pass a single `ImportStats` instance through the entire import batch to ensure monotonic progress reporting across multiple files.
3.  **Memory Guardrail:** While 50k-100k floats fit easily in memory, add a note to use `array.array('f')` or a sampling approach for scores if the dataset exceeds 1M records to keep the memory footprint negligible.
4.  **Actionable Heuristics:** Define specific triggers for the "Threshold Guidance" block (e.g., if the threshold is above the p90, warn the user they are discarding 90% of their data).

### Proposed Revisions to the Plan

```diff
--- original_plan.md
+++ revised_plan.md
@@ -29,12 +29,9 @@
 - Trigger periodic diagnostics by parsed-candidate counts with time fallback.
 - Report when either condition is met:
 - first report at parsed >= 100 or after 30 seconds
-- then every +1000 parsed or after 60 seconds since last report
+- then every +1000 parsed or after 30 seconds since last report (whichever comes first)
 
-4. Bucket granularity
-- Use four buckets aligned with threshold tuning:
-- `[0.0, 0.3)`
-- `[0.3, 0.5)`
-- `[0.5, 0.7)`
-- `[0.7, 1.0]`
+4. Bucket Granularity
+- Use 10 buckets in 0.1 increments (`[0.0, 0.1)`, `[0.1, 0.2)`, ..., `[0.9, 1.0]`).
+- This provides the "shape" of the quality distribution needed for fine-tuning thresholds.
 
 5. Summary percentiles
@@ -75,10 +72,7 @@
   - `quality_p75: float | None`
   - `quality_p90: float | None`
   - `quality_p95: float | None`
-- Bucket counters
-  - `bucket_0_03: int`
-  - `bucket_03_05: int`
-  - `bucket_05_07: int`
-  - `bucket_07_10: int`
+- Bucket counters:
+  - `quality_buckets: dict[int, int]` (index 0-9 representing 0.1 increments)
 - Reservoir state
   - `accepted_seen: int`
@@ -118,21 +112,23 @@
 
 `import_legacy_data(...)` processes both `*-is.txt` and `*-are.txt`.
 
-Requirement:
-- Final telemetry must reflect both files combined.
-
-Implementation approach:
-- Reuse a single `ImportStats` instance across file imports, or
-- merge with a dedicated `merge_import_stats(...)` helper that preserves counters,
-  aggregates, and sample invariants.
+Implementation:
+- Initialize a single `ImportStats` instance at the start of `import_legacy_data`.
+- Pass this instance into each call of `import_factoid_file`.
+- This ensures periodic reports and final summaries reflect the entire batch context.
 
 ### 6) Final Summary Upgrade
 
 In CLI summary section (`main()`), keep current lines and append:
 
 - Quality score overview
   - scored entries
-  - min/avg/max/p50/p75/p90/p95
+  - min/avg/max/p50/p75/p90/p95 (computed by sorting `quality_scores`)
 - Histogram block
-  - each bucket with count + percentage
+  - ASCII bar chart for the 10 buckets
 - Samples block
   - accepted samples (up to 20)
   - rejected samples (up to 20)
 - Threshold guidance block
-  - summarize current threshold behavior from reject rate + percentiles
-  - include practical recommendation text (for example lower, hold, or raise threshold)
+  - If `threshold > p90`: "Warning: Threshold is very aggressive (discarding >90% of data)."
+  - If `threshold < p10`: "Note: Threshold is very permissive (accepting >90% of data)."
+  - Suggest adjusting threshold based on whether rejected samples look "salvageable".
```

I will now proceed with the implementation as described in the revised plan. I'll start by investigating the current implementation of `legacy_import.py`.
