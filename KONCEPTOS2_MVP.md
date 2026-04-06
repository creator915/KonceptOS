# KonceptOS 2.0 MVP

This MVP tests a narrower but more practical idea than the original REPL:

1. Build a structural memory graph from a real repository.
2. Project a local `K = (G, M, I)` around a change.
3. Use that structure for impact analysis.
4. Generate large projects through a manifest-first workflow instead of a single giant prompt.
5. Verify the generated repository continuously so “looks done” is not treated as “is done”.

## Why this MVP exists

The original `konceptos.py` is strongest as a research prototype around FCA-driven
spec editing. It is weaker at real repository ingestion, large-project generation,
and repeatable impact analysis.

`konceptos2_mvp.py` is a fast validation of a different product shape:

- repo-aware
- local-context, not one global hand-maintained table
- manifest-first generation
- graph-backed impact analysis
- dependency-ready generation instead of blind manifest order
- incremental verification snapshots

## Commands

### Web UI

```bash
python3 konceptos2_web.py --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

The Web UI exposes:

- repository ingest
- impact analysis
- manifest planning
- file-by-file generation
- one-shot forge
- real-time snapshot polling
- local run/preview commands
- feedback capture and repair-brief generation

It does not persist your API key to disk. The key is only passed in each request.

### 1. Ingest a repository

```bash
python3 konceptos2_mvp.py ingest . -o konceptos_graph.json
```

This scans supported source files, extracts:

- files
- imports
- defined symbols
- called symbols
- import edges
- basic symbol-use edges

It then saves a structural memory graph as JSON.

### 2. Run impact analysis

```bash
python3 konceptos2_mvp.py impact konceptos_graph.json \
  --changed konceptos.py \
  -o impact_report.json
```

This computes:

- changed files
- impacted files through reverse graph traversal
- unaffected count
- a local K projection around the impacted slice
- FCA concept summaries for that slice

### 3. Plan a large project with OpenRouter

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export OPENROUTER_MODEL="anthropic/claude-opus-4.6"

python3 konceptos2_mvp.py plan \
  mvp_big_project_spec.md \
  -o big_project_manifest.json \
  --target-lines 10000
```

This asks the model for a JSON manifest with:

- project summary
- target stack
- shared contracts
- file list
- file dependencies
- approximate lines per file

### 4. Generate from the manifest

```bash
python3 konceptos2_mvp.py generate \
  big_project_manifest.json \
  --outdir generated_big_project
```

This generates files one at a time using the manifest and already-generated
dependency files as context.

If the run is interrupted, re-running the same command resumes from the files
already written in the output directory.

Generation now:

- waits until declared internal dependencies are ready
- writes incremental reports as files are produced
- re-verifies the partial repository after each step

### 4.5 Verify the output

```bash
python3 konceptos2_mvp.py verify \
  big_project_manifest.json \
  --outdir generated_big_project \
  --require-complete
```

This checks:

- missing files
- manifest dependency violations
- unresolved internal imports
- Python syntax errors
- contract coverage issues
- SQLAlchemy relationship consistency heuristics

### 5. Plan and generate in one step

```bash
python3 konceptos2_mvp.py forge \
  mvp_big_project_spec.md \
  --manifest big_project_manifest.json \
  --outdir generated_big_project \
  --target-lines 10000
```

## Current limitations

- Python parsing is AST-based, but JS/TS/HTML analysis is regex-based.
- Impact analysis is graph-based, not a full semantic proof system.
- The local K projection is intentionally small and task-scoped.
- Large-project generation still depends on model availability and rate limits.
- The requested OpenRouter model may be region-blocked for some keys.

## What to look for when evaluating the MVP

- Does repo ingestion surface useful structure quickly?
- Does local K around a change feel more actionable than a raw graph?
- Does manifest-first generation produce more coherent large outputs than one-shot generation?
- Does the impacted/unaffected split feel directionally correct on real repos?

If those answers are mostly yes, then the product direction is worth deeper work.
