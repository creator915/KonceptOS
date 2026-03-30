# KonceptOS

**Formal Concept Analysis as a development operating system.**

KonceptOS turns the mathematical framework of [Formal Concept Analysis](https://en.wikipedia.org/wiki/Formal_concept_analysis) into a practical tool for building software. Instead of writing requirements documents that drift out of sync with code, you describe your system as a formal context K = (G, M, I) — objects, attributes, and their directed incidence — and let the concept lattice mechanically derive your interface contracts, data flows, execution order, and module boundaries.

Then you ask an LLM to fill in the implementation.

> **The idea:** Clarifying what you're building *is* building it. K is not a spec that precedes code — K is a type system that the code inhabits.

---

## What it does

You start with a requirements document. KonceptOS extracts a coarse formal context K₀ (e.g. 22 functions × 9 concern dimensions). You then **evolve** K by splitting objects and attributes into finer-grained vocabularies, resolving RW (read-write) ambiguities into precise R or W directions. At each step, the concept lattice B(K) is recomputed, revealing which modules must agree on which data contracts.

When K is precise enough, you run `build` and an LLM generates the complete, runnable application from the spec.

```
requirements.md → llm analyze → K₀ (coarse)
                                  ↓
                          resolve / evolve → K (refined)
                                  ↓
                              build → runnable app
```

### What the lattice gives you

- **Interface contracts.** Each concept (A, B) means: all modules in A must agree on the data format of every channel in B.
- **Data flow graph.** Writers and readers on each channel define the complete data flow, derived mechanically from I.
- **Execution order.** Writers must run before readers. The partial order falls out of I; freedom in the order = parallelism.
- **Consistency checks.** A channel with readers but no writer? A writer with no readers? Detected automatically.
- **Impact analysis.** Change K, run `diff`, and get a mathematically exhaustive list of affected modules — and, crucially, modules that are *provably unaffected*.

### Directed incidence

Unlike classical FCA (boolean I), this system uses directed values:

| Value | Meaning |
|-------|---------|
| `0`   | Not involved |
| `R`   | Reads from this channel |
| `W`   | Writes to this channel |
| `RW`  | Both — a sign that the channel description is too coarse |

RW is not a feature of the system; it's a **compression artifact**. Resolving RW entries by splitting objects or attributes into finer vocabulary is the core evolution loop.

### Why this matters — compared to traditional development

In traditional development, dependencies are implicit. They are scattered across import statements, function calls, global variable references, and undocumented conventions. When you change an interface, the blast radius is guessed by human intuition — and things get missed.

In KonceptOS, every dependency is an explicit entry in I. When you modify K, `diff` mechanically and exhaustively lists which incidence values changed, which concepts dissolved (old contracts no longer needed), which concepts emerged (new contracts to establish), and which modules need reimplementation. Most importantly, it lists the modules that are **provably unaffected** — their I values did not change, and that is a mathematical fact, not a judgment call.

Traditional development can only say "I think these modules aren't affected." K says "these modules' I values are unchanged." The difference matters most at scale: a 200-module system where you can prove that 180 modules are untouched by a change is a system you can maintain. A 200-module system where you have to manually verify all 200 is a system that rots.

### Automatic consistency checking

K catches structural errors the moment they are introduced — not at runtime, not in code review, not in production.

**Readers without writers (R_no_W).** A module reads from a channel, but nothing writes to it. Where does the data come from? This is a missing dependency — detected immediately when you inspect `flows`.

**Writers without readers (W_no_R).** A module writes to a channel, but nothing reads it. Dead output — either a module is missing, or the channel is unnecessary.

**Multiple writers on one channel.** Two modules both write to the same atomic channel. This is a race condition waiting to happen — and a signal that the channel is not yet atomic and needs further splitting.

**RW as a consistency signal.** Every RW cell is a flag: the vocabulary is not precise enough here. The count of remaining RW cells (shown in the prompt `K[|G||RW]`) is a live progress indicator of how well-specified the system is.

These checks are not linters bolted onto finished code. They operate on the architecture itself, before any code is written. Problems caught in K cost minutes to fix. The same problems caught in a running system cost days.

### How this differs from current AI coding

Most AI coding tools follow a generate → test → patch loop: describe what you want in natural language, let the LLM generate code, run it, find bugs, ask the LLM to fix them. This works for small programs. It breaks down as systems grow, because:

**No structural memory.** Each generation round starts from scratch or from a context window of prior conversation. The LLM has no formal model of which modules depend on which data — it re-infers these relationships from code every time, and infers them differently each time.

**Architecture drifts silently.** As the LLM patches bugs and adds features, the implicit architecture shifts in ways no one tracks. Module A starts depending on an undocumented side effect of module B. By the time the system reaches 50 modules, the dependency graph is unknowable — a codebase that is commonly described as a "big ball of mud."

**Workflows must be predefined.** Most AI coding frameworks require you to set up explicit pipelines, agent roles, or multi-step workflows before you start. The structure of the development process is decided upfront and imposed on the problem.

KonceptOS takes a different approach:

**K is the structural memory.** The cross table persists across all interactions. Every module's dependencies are explicit entries in I, not inferred from code. When the LLM generates code, it works within the type constraints that K defines — it cannot silently introduce undeclared dependencies.

**Architecture is the first-class artifact.** You evolve K (the architecture) and the code follows. Traditional AI coding evolves code and hopes the architecture stays coherent. When K changes, `diff` tells you exactly what else must change — and what provably does not.

**Structure emerges, it is not prescribed.** You do not predefine an agent workflow or a development pipeline. You start with a requirements document, extract K₀, and evolve it. The concept lattice reveals the system's natural module boundaries, interface contracts, and execution order. The architecture emerges from the domain, not from a framework template.

**Consistency is enforced continuously.** Every time K is modified and `compute` runs, the lattice is recalculated. Structural violations (missing writers, orphan readers, channel conflicts) surface immediately. In a 200-module system, this is the difference between controlled growth and entropy.

This makes KonceptOS particularly suited to larger projects where the main challenge is not writing code — LLMs are already good at that — but maintaining architectural coherence as the system evolves.

---

## Quick start

```bash
python konceptos.py
```

You'll get an interactive REPL:

```
K[0|0]> llm analyze supermario_fca_spec.md
  22 obj, 9 attr
  K: |G|=22 |M|=9 RW=47 ?=0 |B|=52

K[22|47]> ctx          # view the cross table
K[22|47]> rw           # list all RW cells
K[22|47]> resolve obj F13   # split "block system" into subtypes
K[25|50]> resolve attr D    # split "game state" into sub-channels
K[28|42]> compute      # recompute the lattice
K[28|42]> build mario.html  # generate the full app
```

The prompt `K[|G| | RW]` shows you the current object count and remaining RW count at a glance.

### Prerequisites

- Python 3.8+
- An [OpenRouter](https://openrouter.ai/) API key (or modify the `LLM` class for your preferred provider)

```bash
export OPENROUTER_API_KEY="sk-or-v1-your-key-here"
python konceptos.py
```

---

## Command reference

### Building K

| Command | Description |
|---------|-------------|
| `llm analyze <file>` | Extract G, M, I from a requirements document |
| `add obj <id> <name> [\| desc]` | Add an object manually |
| `add attr <id> <name> [\| desc]` | Add an attribute manually |
| `set <obj> <attr> <0\|R\|W\|RW>` | Set an incidence value |
| `row <obj> R,0,W,RW,...` | Batch-set an entire row |
| `compute` | Recompute the concept lattice B(K) |

### Viewing K

| Command | Description |
|---------|-------------|
| `ctx` | Cross table (the core view) |
| `st` | Status summary |
| `rw` | List all RW cells |
| `lat` | Concept lattice hierarchy |
| `concept <n>` | Details of concept n |
| `flows` | Data flow graph |
| `groups` | Coding groups (modules) |

### Evolving K

| Command | Description |
|---------|-------------|
| `resolve obj <id>` | Expand an object (seed-first, LLM fallback) |
| `resolve attr <id>` | Expand an attribute |
| `evolve [n]` | Auto-resolve n RW cells |
| `evolve all` | Resolve all RW cells |

### Seeds

| Command | Description |
|---------|-------------|
| `seed` | View current seed |
| `seed load <file>` | Load a seed JSON |
| `seed save <file>` | Save seed |
| `seed tree` | Show decomposition tree |
| `seed set obj <parent> <c1> <c2> ...` | Add object decomposition rule |
| `seed set attr <parent> <c1> <c2> ...` | Add attribute decomposition rule |

### Build & snapshots

| Command | Description |
|---------|-------------|
| `build [output.html]` | Generate complete runnable code |
| `export <file.md>` | Export spec document |
| `save <file.json>` | Save full state |
| `open <file.json>` | Load state |
| `snaps` | List snapshots |
| `diff <a> <b>` | Compare two snapshots |
| `rollback <n>` | Roll back to snapshot n |

---

## Seeds

A **seed** encodes domain knowledge that guides how K evolves — which decomposition paths to take, what names to use, what incidence directions to expect.

Seeds have three levels:

**Level 1 — Vocabulary.** A set of legal names. When the LLM resolves an object or attribute, it picks from the vocabulary, ensuring naming consistency.

**Level 2 — Decomposition tree + hints.** A tree of how objects and attributes split, plus incidence direction hints (e.g. `"*|collider": "R"` — colliders are always read-only). This is the sweet spot: enough structure to guide evolution, generic enough to apply across projects in the same domain.

**Level 3 — Reference K\*.** A complete atomic-level cross table extracted from a working implementation. New projects can start from K\* and delete/modify.

### Seed lifecycle

```
t=0    Domain expert provides Level 1 (vocabulary)
       → First project is built the hard way
t=1    Extract decomposition decisions from K snapshot chain → Level 2 seed
t=5    Accumulate K* from 5 projects → aggregate into Level 3 seed
t=20   Seed stabilizes → publish
```

Seeds accumulate from use, not from upfront design.

### Example seed

The repository includes `seed_2d_platformer.json` — a Level 2 seed for 2D platformer games. It contains:

- Object vocabulary (game_loop, physics_engine, patrol_enemy, ...)
- Attribute vocabulary (position, velocity, collider, sprite, ...)
- Decomposition trees (entity → player, enemy, collectible, ...)
- Incidence hints (renderer always reads position, never writes it)
- **Conventions** — cross-channel value constraints like jump reachability formulas

Conventions are injected into LLM prompts during `build`, ensuring generated code respects domain physics (e.g. platforms are actually reachable given the gravity and jump speed constants).

---

## Examples

The repository includes two worked examples:

### Super Mario (`supermario_fca_spec.md`)

A full FCA-driven spec for a Super Mario clone. Starting from 22 functions × 9 concern dimensions, evolved through object and attribute splitting to 28 × 16. The concept lattice revealed emergent architecture insights — the "item pipeline" (blocks + props sharing 7/9 attributes), the input bottleneck (only 2/22 functions touch user input), and the "heart cluster" (blocks, props, flagpole as the highest-coupling nodes).

Built output: `mario_v1.html` — a playable Super Mario game in a single HTML file.

### Fireboy & Watergirl (`fireboy_spec.md`)

A two-player cooperative platformer puzzle game. Demonstrates how the same seed (`seed_2d_platformer.json`) applies to a structurally different game — different mechanics (element-based immunity, switches, pushable boxes) but the same underlying concern dimensions.

Built output: `fireboy_v4.html`

---

## Theory in brief

KonceptOS is built on a simple observation: **a software system's complete description is a cross table**.

```
K = (G, M, I)

G = objects (modules / functions)
M = attributes (data channels / concern dimensions)
I : G × M → {0, R, W, RW}
```

The concept lattice B(K) computed from this table is the system's **interface contract hierarchy** — from the coarsest level ("everything is part of the same system") down to the finest ("these two functions must agree on this data channel's format").

K evolves from a coarse K₀ to a fine-grained K\* through **vocabulary replacement**: swapping coarse names for precise ones, refilling I, recomputing B(K). Old concepts may **dissolve** (revealed as artifacts of imprecise vocabulary). New concepts may **emerge** (finer vocabulary exposes previously invisible contracts).

Three forces drive evolution:

1. **Top-down refinement.** Domain knowledge or seeds provide decomposition rules.
2. **Bottom-up feedback.** Implementation reveals missing or incorrect contracts.
3. **Lateral discovery.** Building one module reveals the need for a new data channel.

These forces interleave. K evolution and coding are not sequential — they are woven together.

For a detailed treatment, see `TUTORIAL.md`.

---

## Project structure

```
konceptos.py                  # The engine (single file, ~900 lines)
seed_2d_platformer.json       # Level 2 seed for 2D platformers
supermario_fca_spec.md        # Example: Super Mario FCA spec
fireboy_spec.md               # Example: Fireboy & Watergirl spec
mario_v1.html                 # Example output: playable Mario
fireboy_v4.html               # Example output: playable Fireboy
TUTORIAL.md                   # Step-by-step tutorial (English)
TUTORIAL中文版.md                # Step-by-step tutorial (中文)
```

---

## Roadmap

- [ ] Multi-provider LLM configuration (OpenAI, Anthropic direct, local models)
- [ ] Automated seed extraction from existing codebases (static analysis → K\* → Level 2 seed)
- [ ] Tool/framework binding from K attributes (e.g. "realtime channel → WebSocket not REST")
- [ ] Web UI for cross table editing and lattice visualization
- [ ] Seed marketplace infrastructure

---

## License

[AGPL-3.0](LICENSE)

---

## Citation

If you use KonceptOS in research, please cite:

```
KonceptOS: Formal Concept Analysis as a Development Operating System
```

The theoretical foundation is Formal Concept Analysis (Wille, 1982), extended with directed incidence and vocabulary-replacement evolution.
