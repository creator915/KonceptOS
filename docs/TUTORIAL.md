# KonceptOS Tutorial

This tutorial walks through the complete KonceptOS workflow: building an application from a requirements document, extracting reusable domain knowledge into a seed, and using that seed to build a second application with significantly less effort.

By the end you will understand how K evolves, when to intervene manually, and why seeds are the compound interest of this approach.

## Prerequisites

- Python 3.8+
- An OpenRouter API key (or modify the `LLM` class for another provider)

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
python konceptos.py
```

---

## Part 1 — Building without a seed

The first project in any domain is the hard one. There is no seed yet, so every decomposition decision must be made from scratch. This is normal. The goal is not just to ship the project — it is to learn the domain's structure well enough to encode it for next time.

We will use a 2D platformer (Super Mario clone) as the running example.

### Step 1: Extract K₀ from a requirements document

Every project starts with a plain-language requirements document. It does not need to be formal — a few pages describing what the system should do is enough.

```
K[0|0]> llm analyze supermario_fca_spec.md
  22 obj, 9 attr
  K: |G|=22 |M|=9 RW=47 ?=0 |B|=52
```

The LLM reads the document and produces an initial cross table K₀ with 22 objects (modules/functions), 9 attributes (data channels), and 47 RW cells. The prompt `K[22|47]` shows these two numbers at a glance: how many objects exist, and how many RW cells remain.

Inspect what was extracted:

```
K[22|47]> ctx          # view the cross table
K[22|47]> st           # status summary
K[22|47]> rw           # list all RW cells
```

47 RW cells means 47 places where the description is too coarse — some module is marked as both reading and writing a channel, which usually means the channel conflates two different data flows.

### Step 2: Evolve K by resolving RW

The core loop is vocabulary replacement: swap a coarse name for finer-grained names, refill the incidence values, recompute the concept lattice.

**Splitting objects.** Start with an object that has many RW entries:

```
K[22|47]> resolve obj F13
  brick  question_block  hidden_block  empty_block
```

The `resolve` command asks the LLM to decompose "block system" into subtypes. The LLM may suggest too many or too few — use the `edit` prompt to trim. In this case, four subtypes capture the domain well.

Key principle: **split by domain semantics, not by R/W direction.** "Block system" splits into brick, question block, hidden block, empty block — because those are different things in the game world. Splitting into "block-reader" and "block-writer" is meaningless.

**Splitting attributes.** Some RW cells disappear when objects are split, but others remain because the attribute itself is too coarse:

```
K[25|50]> resolve attr D
  powerup_state  score  lives  timer
```

"Game state" was a single attribute. After splitting into power-up state, score, lives, and timer, the old RW entries resolve: blocks *read* power-up state (to decide which item to spawn) and *write* score (when destroyed). These were two different data flows compressed into one name.

**Splitting physics:**

```
K[28|53]> resolve attr B
  position  velocity  collider
```

"Spatial physics" becomes position, velocity, and collider — three channels with very different read/write patterns.

### Step 3: Manual correction

The LLM will sometimes assign wrong directions. After splitting physics into position, velocity, and collider, the LLM marked collider as RW for many objects. But colliders are defined at initialization and never change at runtime — they should all be R.

```
K[28|58]> set F09 B_3 R      # collision detector only reads colliders
K[28|57]> set F11 B_3 R      # enemies only read colliders
...
K[28|49]> compute
```

Nine manual corrections, each based on domain knowledge: "colliders are constants." This is the second evolutionary force — bottom-up feedback from understanding the domain. The `compute` command recomputes the concept lattice after changes.

### Step 4: Knowing when to stop

K does not need to reach the theoretical atomic level K\* before building. The question is whether the current K captures enough structure for the LLM to generate correct code.

A practical heuristic: if the remaining RW cells are in areas where ambiguity does not affect implementation (e.g., a UI element that both reads and writes a display buffer), they can stay. If RW cells sit at architectural boundaries (e.g., between physics and rendering), resolve them.

```
K[28|47]> build mario.html
```

The `build` command sends the current K — with its objects, attributes, incidence table, and any loaded seed conventions — to the LLM, which generates a complete runnable application.

### Step 5: Test and iterate

Test the output. If something is wrong, the fix goes through K:

```
# discovered that collision events need to carry direction info
K[28|47]> resolve attr col_ev
  col_type col_pos
K[28|45]> compute
K[28|45]> diff 3 4          # compare snapshot 3 (before) with 4 (after)
```

The `diff` command shows exactly which modules are affected by the change — and which are provably unaffected. Only the affected modules need regeneration.

### Lessons from the first project

Several patterns emerge during a first build without a seed:

- The LLM's initial decomposition suggestions are a starting point, not a final answer. Expect to `edit` most of them.
- Direction errors (marking constants as RW) are the most common LLM mistake. Domain knowledge catches them.
- Splitting audio into sfx/bgm, lifecycle into alive/spawn, and physics into position/velocity/collider are decisions that will apply to *every* 2D platformer — not just this one.
- The decomposition tree (what splits into what) and direction hints (colliders are always R) are reusable knowledge.

This is the raw material for a seed.

---

## Part 2 — Extracting a seed

After the first project ships, its K snapshot chain contains every decomposition decision that was made. A seed encodes these decisions so they can be replayed on future projects.

### What goes into a seed

A Level 2 seed (the practical sweet spot) contains four things:

**1. Object vocabulary** — the legal names for modules in this domain:

```json
{
  "obj_vocab": [
    "game_loop", "input_manager", "physics_engine",
    "collision_detector", "renderer", "player_character",
    "patrol_enemy", "collectible", "gui_hud"
  ]
}
```

**2. Attribute vocabulary** — the legal names for data channels:

```json
{
  "attr_vocab": [
    "position", "velocity", "collider", "sprite",
    "animation_state", "input_state", "score", "lives"
  ]
}
```

**3. Decomposition trees** — how coarse names split into fine ones:

```json
{
  "obj_tree": {
    "entity": ["player_character", "enemy", "collectible"],
    "enemy": ["patrol_enemy", "flying_enemy", "stationary_enemy"]
  },
  "attr_tree": {
    "physics": ["position", "velocity", "collider"],
    "game_state": ["score", "lives"]
  }
}
```

**4. Incidence hints** — direction constraints that prevent common LLM errors:

```json
{
  "incidence_hints": {
    "*|collider": "R",
    "renderer|position": "R",
    "renderer|sprite": "R",
    "input_manager|input_state": "W",
    "physics_engine|position": "W"
  }
}
```

The wildcard `*|collider: R` means "no matter what object, collider is always read-only." This single hint prevented nine manual corrections in the first project.

### Conventions

Seeds can also carry **conventions** — cross-channel value constraints that the LLM must respect during code generation:

```json
{
  "conventions": [
    "JUMP REACHABILITY: max_jump_height = jump_speed^2 / (2 * gravity). Every platform must be reachable.",
    "UNIFORM GRAVITY: All entities use the same gravity constant.",
    "TWO-PLAYER CONTROLS: Use non-conflicting key sets (WASD + Arrow keys)."
  ]
}
```

Conventions are injected into LLM prompts during `build`. They encode domain physics and design rules that the LLM would otherwise violate (e.g., placing platforms too high to jump to).

### Saving the seed

```
K[28|47]> seed save seed_2d_platformer.json
```

The seed is a JSON file. It can be version-controlled, shared, and improved over time.

---

## Part 3 — Building with a seed

The second project in the same domain demonstrates the payoff. We build a Fireboy & Watergirl clone — a structurally different game (two-player cooperative puzzle platformer with element-based mechanics) that shares the same underlying concern dimensions as the Mario clone.

### Step 1: Load the seed, then analyze

```
K[0|0]> seed load seed_2d_platformer.json
K[0|0]> llm analyze fireboy_spec.md
  18 obj, 9 attr
  K: |G|=18 |M|=9 RW=38 ?=0 |B|=44
```

The seed is loaded before analysis. The LLM now has access to the vocabulary, decomposition trees, and incidence hints from the first project.

### Step 2: Evolve — guided by the seed

When resolving objects and attributes, `resolve` checks the seed's decomposition tree first. If a matching rule exists, it applies immediately without calling the LLM:

```
K[18|38]> resolve attr B
  position velocity collider       # from seed, no LLM call needed
```

The seed knew that "physics" splits into position, velocity, and collider. This was a decision that required thought during the Mario project; now it is automatic.

The incidence hints also fire: collider is set to R everywhere, preventing the direction errors that required nine manual fixes last time.

### Step 3: Domain-specific additions

The seed handles the generic 2D platformer structure. What remains is game-specific: element immunity (fire/water/poison), switches and doors, pushable boxes. These require new objects and attributes that are not in the seed:

```
K[22|30]> add attr element_type
K[22|30]> add obj switch_mechanism
K[23|28]> set switch_mechanism element_type R
```

The seed does not eliminate domain-specific work — it eliminates re-doing generic work.

### Step 4: Build

```
K[25|18]> build fireboy.html
```

The RW count dropped faster (38 → 18 vs. 47 → 47 in the first project at equivalent stages), fewer manual corrections were needed, and the decomposition steps required less judgment because the seed provided the vocabulary.

### What the seed changed

Concretely, the seed contributed:

- **Zero LLM calls** for decompositions that matched the tree (physics, audio, lifecycle, game state).
- **Zero manual direction fixes** for channels covered by incidence hints (collider, renderer inputs, input_state).
- **Consistent naming** across projects — `position` instead of `pos` or `location` or `coordinates`, because the vocabulary constrains the LLM's choices.
- **Convention enforcement** — the generated code respects jump reachability formulas and uses non-conflicting key bindings for two players, because conventions were injected into the build prompt.

The structural decisions that took eight steps and nine manual corrections in Part 1 were handled automatically. The developer's attention went to what is genuinely new: element mechanics, cooperative puzzle design, switch-door wiring.

---

## Part 4 — The evolution loop in detail

This section unpacks the mechanics that Parts 1–3 moved through quickly.

### Reading the cross table

The `ctx` command shows the core data structure:

```
         pos  vel  col  spr  anim input score lives
physics   W    R    R    0    0    0     0     0
renderer  R    0    R    R    R    0     0     0
input     0    0    0    0    0    W     0     0
player    R    W    R    R    R    R     W     0
enemy     R    W    R    R    R    0     0     0
hud       0    0    0    0    0    0     R     R
```

Each row is a module. Each column is a data channel. R means the module reads from that channel; W means it writes. This table *is* the system's architecture.

### What the concept lattice reveals

Running `compute` after changes recalculates the concept lattice B(K). Each concept (A, B) is a maximal rectangle in the cross table: A is a set of modules that all share the attributes in B.

```
K[25|18]> lat
  Concept 0: ({physics, renderer, player, enemy}, {pos, col})
  Concept 1: ({player, enemy}, {pos, vel, col, spr, anim})
  Concept 2: ({renderer}, {pos, col, spr, anim, camera})
  ...
```

Concept 0 says: physics, renderer, player, and enemy all interact with both position and collider — they must agree on the data format of these two channels. This is an interface contract derived mechanically from the table.

### Data flow from the table

The `flows` command derives the data flow graph:

```
K[25|18]> flows
  input_state:  input_manager → player
  velocity:     player → physics, enemy → physics
  position:     physics → renderer, physics → collision_detector
  score:        player → hud
```

Writers produce data, readers consume it. The complete data flow is read off from I — no additional specification needed.

### Execution order from the table

Writers must execute before readers:

```
input_manager (writes input_state)
  → player (reads input_state, writes velocity)
    → physics (reads velocity, writes position)
      → renderer (reads position)
      → collision_detector (reads position)
```

Modules without ordering constraints can run in parallel. Cycles in the ordering graph indicate frame boundaries — not errors, since a game loop is inherently a cross-frame feedback loop.

### The three forces that drive evolution

**Top-down refinement:** The seed or domain knowledge says "physics should split into position, velocity, collider." Apply the rule, refill I, recompute.

**Bottom-up feedback:** While implementing collision detection, you realize collision events need to carry direction information. This means `collision_event` should split into `collision_type` and `collision_direction`. Modify K, run `diff`, rebuild only the affected modules.

**Lateral discovery:** While implementing enemy rendering, you realize you need a "squash progress" channel for the stomp animation. Add the attribute to K, set the incidence values, recompute. New contracts emerge: the stomp handler and the enemy renderer must agree on the squash progress format.

These three forces interleave throughout development. K evolution and coding are not sequential phases — they are woven together.

---

## Part 5 — Seed lifecycle

Seeds improve with use. The trajectory:

**t=0** — No seed exists. Build the first project manually, making every decomposition decision from scratch. This is the investment.

**t=1** — Extract a Level 2 seed from the first project's K snapshot chain. The seed captures decomposition trees, direction hints, and conventions. Future projects in the same domain start here.

**t=5** — After five projects, the seed stabilizes. Edge cases have been encountered and encoded. The vocabulary is comprehensive. Incidence hints cover all common direction errors.

**t=20** — The seed is mature. It encodes years of domain experience in a machine-readable format. New projects in the domain require only game-specific additions; the generic structure is fully automated.

The included `seed_2d_platformer.json` is at roughly t=2 — extracted from two projects (Mario and Fireboy), covering core platformer structure but not yet handling every edge case.

---

## Quick reference

| Stage | What to do | Commands |
|-------|-----------|----------|
| Start | Load seed (if available), analyze requirements | `seed load`, `llm analyze` |
| Inspect | Review the cross table and RW cells | `ctx`, `st`, `rw` |
| Evolve | Split objects and attributes to resolve RW | `resolve obj`, `resolve attr` |
| Correct | Fix LLM direction errors | `set`, `row` |
| Check | Recompute lattice, review contracts | `compute`, `lat`, `flows` |
| Build | Generate the application | `build` |
| Test | Find issues, modify K, diff, rebuild | `set`, `compute`, `diff`, `build` |
| Extract | Save seed for future projects | `seed save` |

---

## Common pitfalls

**Splitting by R/W direction instead of domain semantics.** If you split "block system" into "block-reader" and "block-writer," you get two objects that have no domain meaning. Split into brick, question block, hidden block — things that exist in the game world.

**Trusting LLM direction assignments blindly.** The LLM will mark runtime constants (colliders, map data, level structure) as RW. Check `rw` after every `resolve` and correct these manually.

**Over-resolving.** Not every RW cell needs to be resolved before `build`. If the ambiguity does not affect code correctness at the current abstraction level, leave it. You can always refine later.

**Under-using seeds.** If you are building your second project in a domain and not using a seed from the first, you are re-doing work. Even a Level 1 seed (just a vocabulary list) prevents naming drift.

**Ignoring conventions.** Seeds without conventions produce code that compiles but does not work — platforms too high to jump to, collision boxes that do not fit through passages, conflicting key bindings. Conventions are not optional polish; they are domain physics.
