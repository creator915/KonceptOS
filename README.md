# KonceptOS

**Formal Concept Analysis as structural memory for AI software delivery.**

This branch turns KonceptOS from a pure FCA REPL prototype into a more practical
`KonceptOS 2.0 MVP`:

- ingest a real repository into a structural graph
- project a local `K = (G, M, I)` around a change
- plan a large project as a manifest with explicit contracts
- generate files only when their internal dependencies are ready
- verify the generated repository continuously to catch drift and fake progress

The original `konceptos.py` is still here as the research prototype.
The new workflow lives in:

- `konceptos2_mvp.py`
- `konceptos2_web.py`
- `webui/index.html`

---

## Why this branch exists

Two practical problems showed up when trying to use KonceptOS for bigger AI coding tasks:

1. **Information distorts while it is passed from requirements -> plan -> files -> code.**
2. **A module can look finished in code, but still be wrong at runtime or UX level.**

This branch attacks those two problems directly.

### Anti-distortion

Instead of asking for a giant codebase in one prompt, the system now works through
explicit artifacts:

```text
requirements -> manifest -> contracts -> file generation -> repo re-ingest -> verification
```

The key idea is that generation should not be a pure prompt chain.
After each step, the repository is re-read as structure again.

### Anti-fake-completion

A generated file is not treated as “done” just because text exists on disk.
The MVP now checks:

- manifest dependency closure
- unresolved internal imports
- Python syntax validity
- selected shared-contract coverage
- SQLAlchemy `back_populates` consistency heuristics

This is still only the first validation layer, but it is materially stronger than
“the model wrote something that looks plausible.”

---

## What is in this repo

### 1. Original REPL prototype

`konceptos.py` is the original single-file engine:

- extract `K₀` from a requirements document
- evolve K through vocabulary replacement
- compute the FCA concept lattice
- generate a runnable example app

It is still valuable as the mathematical core and as a compact demo of the original idea.

### 2. KonceptOS 2.0 MVP

`konceptos2_mvp.py` adds a more product-like workflow:

- `ingest`: scan a repo into a structural memory graph
- `impact`: compute a local K and an impact report for changed files
- `plan`: ask OpenRouter for a manifest-first architecture
- `generate`: generate files in dependency-ready order with incremental snapshots
- `verify`: verify the generated repository against the manifest
- `forge`: `plan + generate + ingest`

### 3. Local Web UI

`konceptos2_web.py` and `webui/index.html` provide a no-dependency local workbench for:

- repo ingest
- impact analysis
- project planning
- generation
- verification

---

## Quick start

### Original FCA REPL

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export OPENROUTER_MODEL="anthropic/claude-opus-4.6"
python3 konceptos.py
```

### KonceptOS 2.0 MVP CLI

```bash
python3 konceptos2_mvp.py ingest . -o konceptos_graph.json

python3 konceptos2_mvp.py impact konceptos_graph.json \
  --changed konceptos.py \
  -o konceptos_impact.json
```

### Manifest-first planning

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
export OPENROUTER_MODEL="anthropic/claude-opus-4.6"
export OPENROUTER_TIMEOUT_SECONDS=600

python3 konceptos2_mvp.py plan \
  mvp_big_project_spec.md \
  -o big_project_manifest.json \
  --target-lines 10000
```

### Dependency-ready generation

```bash
python3 konceptos2_mvp.py generate \
  big_project_manifest.json \
  --outdir generated_big_project
```

Generation now writes incremental reports and snapshots as it goes.
If the run is interrupted, re-running the command resumes from the files already present.

### Verification

```bash
python3 konceptos2_mvp.py verify \
  big_project_manifest.json \
  --outdir generated_big_project \
  --require-complete
```

### Web UI

```bash
python3 konceptos2_web.py --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.

---

## The 2.0 MVP workflow

### Step 1: Ingest a real repo

The repository is scanned into a structural graph:

- files
- imports
- defined symbols
- called symbols
- import edges
- basic symbol-use edges

This graph acts as the first layer of structural memory.

### Step 2: Project a local K

For a proposed change, the system computes:

- changed files
- impacted files through reverse traversal
- a local `K = (G, M, I)` around the affected slice
- FCA concept summaries for that local neighborhood

This is the bridge between real code and the original KonceptOS math.

### Step 3: Plan before generating

Large project generation starts from a **manifest**, not direct code generation.

Each manifest file entry includes:

- `path`
- `purpose`
- `depends_on`
- `contracts_in`
- `contracts_out`
- `approx_lines`
- `verification`

This makes the plan inspectable before code exists.

### Step 4: Generate only when ready

The generator no longer blindly follows manifest order.
It now generates a file only when its declared internal dependencies are already available.

That change is important because it reduces one major source of information drift:
files referring to internal modules that do not exist yet.

### Step 5: Re-ingest and verify after each step

After generation steps, the repo is checked again.
The report tracks:

- missing files
- dependency violations
- unresolved internal imports
- syntax errors
- relationship consistency issues
- contract issues

This is the beginning of the “module is actually done” loop.

---

## Why this is closer to a real product

The original KonceptOS REPL was strongest at:

- formalizing architecture
- exposing hidden contracts
- showing how seeds compound across projects

The new MVP keeps that spirit, but adds the missing operational layer:

- real repo ingestion
- incremental generation
- verification after generation
- resumable long-running workflows
- a simple UI for repeated use

In other words:

**KonceptOS 1.x:** evolve K, then ask the model to code.  
**KonceptOS 2.0 MVP:** evolve structure, generate with dependency discipline, then verify continuously.

---

## Current limitations

This is still an MVP.

- Python ingestion is AST-based; JS/TS/HTML ingestion is still regex-heavy.
- Verification is structural/static first; runtime and UX oracles are still limited.
- The local K projection is task-scoped, not a complete semantic proof.
- Model availability still depends on OpenRouter region/model policy.
- The original `konceptos.py` lattice computation is still heuristic, not a complete FCA enumerator.

---

## Suggested next steps

If you want to push this further, the next useful steps are:

1. Add stronger runtime validators and UI oracles.
2. Re-project local K after every batch, not only for manual impact analysis.
3. Promote shared contracts from prompt hints to executable schema checks.
4. Split generation into bounded agents that are assigned only dependency-ready slices.
5. Turn snapshots into a first-class history browser in the web UI.

---

## Files of interest

Core:

- `konceptos.py`
- `konceptos2_mvp.py`
- `konceptos2_web.py`
- `webui/index.html`

Docs:

- `README.md`
- `KONCEPTOS2_MVP.md`
- `TUTORIAL.md`
- `TUTORIAL中文版.md`

Examples:

- `seed_2d_platformer.json`
- `supermario_fca_spec.md`
- `fireboy_spec.md`
- `mario_v1.html`
- `fireboy_v4.html`

---

## License

[AGPL-3.0](LICENSE)
