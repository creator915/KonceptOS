# KonceptOS CLI

> K -> K* by vocabulary replacement + redescription. FCA-based concept evolution CLI.

KonceptOS is a command-line tool built on **Formal Concept Analysis (FCA)** that evolves an initial concept context K into a refined context K\* by iteratively resolving compression artifacts (RW cells) through vocabulary replacement and redescription, and ultimately generates runnable applications from the specification.

## Install

```bash
npm install -g konceptos-cli
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KONCEPTOS_API_KEY` | - | LLM API key (required for LLM features) |
| `KONCEPTOS_MODEL` | `glm-5` | Model name |
| `KONCEPTOS_URL` | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | API endpoint |

## Core Concepts

- **K = (G, M, I)**: A formal context with objects (G), attributes (M), and incidence (I)
- **Incidence values**: `0` (none), `R` (read), `W` (write), `RW` (read+write = compression artifact)
- **K\***: The target refined context where all RW cells are resolved
- **Seed**: Predefined decomposition rules, conventions, and vocabulary hints
- **Resolve/Evolve**: Expand compressed concepts into finer-grained sub-concepts

## Workflow

```bash
# 1. Extract objects, attributes, and incidence from a document
konceptos llm analyze requirements.txt

# 2. Check status
konceptos st

# 3. Resolve all RW compressions
konceptos evolve all

# 4. Generate application
konceptos build app.html
```

## Commands

### Basics

```bash
konceptos add obj <id> <name> [-d desc]   # Add object
konceptos add attr <id> <name> [-d desc]  # Add attribute
konceptos set <oid> <aid> <0|R|W|RW>      # Set incidence
konceptos row <oid> <vals>                # Set row (comma-separated)
konceptos del obj|attr <id>               # Delete object/attribute
konceptos bind <aid> <tech>               # Bind attribute to technology
konceptos convention [text...]            # Set/view conventions
```

### View

```bash
konceptos ctx          # Context table (incidence matrix)
konceptos st           # Status overview
konceptos rw           # List RW cells
konceptos flows        # Data flows (W -> R)
konceptos groups       # Coding groups by concept
konceptos lat          # Concept lattice
konceptos concept <n>  # Concept detail
konceptos hist         # Operation history
```

### Seed

```bash
konceptos seed                                    # Seed summary
konceptos seed load <file>                        # Load seed JSON
konceptos seed save <file>                        # Save seed
konceptos seed tree                               # Show decomposition trees
konceptos seed conv                               # Show seed conventions
konceptos seed set obj <parent> <child1> <child2> ...   # Define object decomposition
konceptos seed set attr <parent> <child1> <child2> ...  # Define attribute decomposition
```

### LLM

```bash
konceptos llm analyze <file>   # Extract G, M, I from document
konceptos llm ask              # Fill unknowns interactively (manual + LLM)
konceptos llm chat <msg>       # Chat with FCA assistant
```

### Resolve & Evolve

```bash
konceptos resolve obj <id>     # Expand object (seed -> LLM fallback)
konceptos resolve attr <id>    # Expand attribute (seed -> LLM fallback)
konceptos evolve               # Auto-resolve 1 RW cell
konceptos evolve <n>           # Auto-resolve n rounds
konceptos evolve all           # Resolve until K* or stuck
```

### Build

```bash
konceptos build [out.html]     # Generate runnable HTML app from FCA spec
```

### Snapshots & System

```bash
konceptos snaps                # List snapshots
konceptos diff <a> <b>         # Diff two snapshots
konceptos rollback <n>         # Rollback to snapshot
konceptos compute              # Recompute FCA lattice
konceptos save <file>          # Save state to file
konceptos open <file>          # Load state from file
konceptos export <file>        # Export FCA spec as markdown
```

## Data Storage

State is stored in `.konceptos/state.json` in the current working directory, automatically read/written on each command.

## License

MIT
