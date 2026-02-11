# Legacy Import

This document describes the implemented legacy factoid importer and its
quality telemetry behavior.

## Supported Input

The importer reads legacy factoid text files in `topic => information` format:

- `<botname>-is.txt`
- `<botname>-are.txt`

When `--botname` is omitted, files are auto-detected using `*-is.txt` and
`*-are.txt` in the source directory.

## CLI Usage

```bash
python -m infobot.tools \
  --source /path/to/legacy/data \
  --database data/infobot.db \
  --quality-threshold 0.30 \
  --botname infobot \
  --verbose
```

Arguments:

- `--source` (required): directory containing legacy files
- `--database`: sqlite path (default `data/infobot.db`)
- `--botname`: optional file prefix (for `<botname>-is.txt` and `<botname>-are.txt`)
- `--quality-threshold`: minimum accepted quality score in `[0.0, 1.0]`
- `--verbose`: enables debug-level importer logging

## Quality Telemetry Model

Every parsed candidate is scored, then tracked regardless of acceptance:

- score counters and sum
- min/avg/max scores
- 10-bucket score distribution (`0.0-0.1` through `0.9-1.0`)
- approximate percentiles (`p50`, `p75`, `p90`, `p95`)
- accepted/rejected counters
- accepted/rejected sample reservoirs (bounded, deterministic sampling)

Telemetry is accumulated in one shared `ImportStats` instance across both `is`
and `are` file imports, so final metrics are globally representative.

## Periodic Diagnostics During Import

The importer emits periodic quality diagnostics while running. Emission happens
on either cadence:

- parsed-candidate cadence: every 500 parsed candidates
- elapsed-time cadence: every 30 seconds (monotonic clock)

Each diagnostic snapshot includes:

- parsed/imported/rejected totals
- reject rate
- threshold in use
- score min/avg/max
- compact 10-bucket histogram
- accepted sample preview line
- rejected sample preview line

The sample preview format is:

- `<key>@<line> (score=<score>) -> <value preview>`

Up to 3 sampled previews are shown per accepted/rejected section per snapshot.

## Final Summary Output

At completion, the CLI summary includes:

- core counts (`parsed`, `imported`, `duplicates`, `errors`, etc.)
- scored/accepted/rejected candidate counts
- reject rate
- score min/avg/max
- percentiles (`p50/p75/p90/p95`)
- full histogram line
- full 10-bucket count/percentage breakdown
- accepted sample previews
- rejected sample previews
- threshold guidance block

## Threshold Guidance Semantics

Guidance is derived from observed score distribution:

- low confidence: fewer than 50 scored candidates
- medium confidence: 50 or more scored candidates

Heuristics:

- reject rate `> 80%`: suggest lowering threshold toward `p50`
- reject rate `< 5%`: suggest raising threshold toward `p90`
- otherwise: keep current threshold

For low-confidence runs, the summary explicitly shows guardrail messaging and
withholds recommendation changes.

## Environment Variables

Two environment variables control quality sampling behavior:

- `LEGACY_IMPORT_SAMPLE_CAP`
  - integer, default `20`
  - must be `>= 0`
  - max retained samples per accepted/rejected reservoir

- `LEGACY_IMPORT_RNG_SEED`
  - integer, default `1337`
  - controls deterministic reservoir sampling
  - useful for reproducible diagnostics during testing/tuning
