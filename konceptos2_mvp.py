#!/usr/bin/env python3
"""
KonceptOS 2.0 MVP

This is a practical bridge between the original KonceptOS FCA REPL and a
structure-aware coding workflow for real repositories.

Capabilities:
- Ingest a repository into a structural memory graph
- Project a local K around changed files and compute FCA concepts
- Run graph-based impact analysis
- Plan a large project as a manifest-first architecture
- Generate code file-by-file from the manifest through OpenRouter
"""

import argparse
import ast
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, deque
from pathlib import Path

from konceptos import FCA, extract_json


DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-opus-4.6")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".nuxt",
    ".turbo",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
}
TEXT_SUFFIXES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}
KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "function",
    "return",
    "typeof",
    "new",
    "class",
    "import",
}
MANIFEST_SCHEMA = {
    "project_name": "string",
    "summary": "string",
    "target_stack": "object",
    "shared_contracts": "array",
    "files": "array",
}


def eprint(msg):
    print(msg, file=sys.stderr)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def strip_fences(text):
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def safe_rel(path, root):
    return str(Path(path).resolve().relative_to(Path(root).resolve()))


def default_verification_for_file(item):
    path = item["path"]
    suffix = Path(path).suffix.lower()
    smoke = "exists"
    if suffix == ".py":
        smoke = "python_syntax"
    elif suffix in {".yml", ".yaml", ".json"}:
        smoke = "config_shape"
    elif path.endswith("Dockerfile"):
        smoke = "docker_build_contract"
    elif suffix in {".md"}:
        smoke = "doc_exists"
    return {
        "smoke": smoke,
        "acceptance": [
            f"{path} must not rely on undeclared internal dependencies.",
            f"{path} must satisfy its declared contracts_in/contracts_out.",
        ],
    }


def normalize_verification_block(item):
    block = item.get("verification") or {}
    if not isinstance(block, dict):
        block = {}
    merged = default_verification_for_file(item)
    merged.update({k: v for k, v in block.items() if k != "acceptance"})
    acceptance = list(merged.get("acceptance", []))
    acceptance.extend(block.get("acceptance", []))
    merged["acceptance"] = acceptance
    return merged


def manifest_file_map(manifest):
    return {item["path"]: item for item in manifest["files"]}


def selected_manifest_files(manifest, max_files=None):
    return manifest["files"][: max_files or len(manifest["files"])]


def selected_manifest_paths(manifest, max_files=None):
    return [item["path"] for item in selected_manifest_files(manifest, max_files=max_files)]


def internal_manifest_dependencies(file_spec, selected_path_set):
    return [dep for dep in file_spec["depends_on"] if dep in selected_path_set]


class OpenRouterClient:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.timeout_seconds = int(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "600"))

    def require_key(self):
        if not self.api_key:
            raise RuntimeError("Missing OpenRouter API key. Set OPENROUTER_API_KEY.")

    def chat(self, system, user, max_tokens=32000):
        self.require_key()
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self.api_key,
            "HTTP-Referer": "https://konceptos.local",
            "X-Title": "KonceptOS 2.0 MVP",
        }
        req = urllib.request.Request(OPENROUTER_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {body[:500]}") from exc
        except Exception as exc:
            raise RuntimeError(f"OpenRouter request failed: {exc}") from exc


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imports = []
        self.defines = set()
        self.calls = set()

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        level = "." * node.level
        joined = level + module if module else level or ""
        if joined:
            self.imports.append(joined)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defines.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defines.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.defines.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        name = self._call_name(node.func)
        if name:
            self.calls.add(name)
        self.generic_visit(node)

    def _call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None


def analyze_python(text):
    info = {"imports": [], "defines": [], "calls": []}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return info
    visitor = PythonAnalyzer()
    visitor.visit(tree)
    info["imports"] = sorted(set(visitor.imports))
    info["defines"] = sorted(visitor.defines)
    info["calls"] = sorted(visitor.calls)
    return info


def regex_unique(pattern, text, flags=0):
    found = set()
    for match in re.finditer(pattern, text, flags):
        name = match.group(1)
        if name and name not in KEYWORDS:
            found.add(name)
    return sorted(found)


def analyze_web(text, language):
    info = {"imports": [], "defines": [], "calls": []}
    info["imports"] = sorted(
        set(
            re.findall(r"""from\s+['"]([^'"]+)['"]""", text)
            + re.findall(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", text)
            + re.findall(r"""import\(\s*['"]([^'"]+)['"]\s*\)""", text)
        )
    )
    info["defines"] = sorted(
        set(
            regex_unique(r"""function\s+([A-Za-z_]\w*)\s*\(""", text)
            + regex_unique(r"""class\s+([A-Za-z_]\w*)\s*[{(]""", text)
            + regex_unique(r"""const\s+([A-Za-z_]\w*)\s*=""", text)
            + regex_unique(r"""let\s+([A-Za-z_]\w*)\s*=""", text)
            + regex_unique(r"""var\s+([A-Za-z_]\w*)\s*=""", text)
        )
    )
    info["calls"] = sorted(regex_unique(r"""([A-Za-z_]\w*)\s*\(""", text))
    if language == "html":
        info["imports"] = sorted(
            set(
                info["imports"]
                + re.findall(r"""<script[^>]+src=['"]([^'"]+)['"]""", text)
                + re.findall(r"""<link[^>]+href=['"]([^'"]+)['"]""", text)
            )
        )
    return info


def classify_file(path):
    return TEXT_SUFFIXES.get(path.suffix.lower())


def should_skip(path):
    return any(part in SKIP_DIRS for part in path.parts)


def repo_files(root):
    root = Path(root)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path.relative_to(root)):
            continue
        language = classify_file(path)
        if language:
            yield path, language


def relative_import_to_path(root, file_path, spec):
    if not spec:
        return None
    if file_path.suffix == ".py":
        return resolve_python_import(root, file_path, spec)
    return resolve_path_like_import(root, file_path, spec)


def python_import_candidates(root, file_path, spec):
    root = Path(root)
    base_dir = file_path.parent
    if spec.startswith("."):
        dots = len(spec) - len(spec.lstrip("."))
        remainder = spec[dots:]
        anchor = base_dir
        for _ in range(max(dots - 1, 0)):
            anchor = anchor.parent
        parts = [p for p in remainder.split(".") if p]
        target = anchor.joinpath(*parts) if parts else anchor
    else:
        parts = [p for p in spec.split(".") if p]
        target = root.joinpath(*parts)
    return [target.with_suffix(".py"), target / "__init__.py"]


def resolve_python_import(root, file_path, spec):
    for candidate in python_import_candidates(root, file_path, spec):
        if candidate.exists():
            return safe_rel(candidate, root)
    return None


def path_like_import_candidates(root, file_path, spec):
    base = (file_path.parent / spec).resolve()
    return [
        base,
        base.with_suffix(".js"),
        base.with_suffix(".jsx"),
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base.with_suffix(".json"),
        base / "index.js",
        base / "index.ts",
        base / "index.tsx",
    ]


def resolve_path_like_import(root, file_path, spec):
    if not spec.startswith("."):
        return None
    for candidate in path_like_import_candidates(root, file_path, spec):
        if candidate.exists() and candidate.is_file():
            return safe_rel(candidate, root)
    return None


def ingest_repository(root):
    root = Path(root).resolve()
    files = {}
    for path, language in repo_files(root):
        rel = safe_rel(path, root)
        text = read_text(path)
        if language == "python":
            analysis = analyze_python(text)
        else:
            analysis = analyze_web(text, language)
        files[rel] = {
            "path": rel,
            "language": language,
            "lines": len(text.splitlines()),
            "bytes": len(text.encode("utf-8")),
            "imports": analysis["imports"],
            "resolved_imports": [],
            "defines": analysis["defines"],
            "calls": analysis["calls"],
            "segments": list(Path(rel).parts[:-1]),
        }
    for rel, info in files.items():
        src_path = root / rel
        resolved = []
        for spec in info["imports"]:
            target = relative_import_to_path(root, src_path, spec)
            if target and target in files:
                resolved.append(target)
        info["resolved_imports"] = sorted(set(resolved))
    symbol_to_files = {}
    for rel, info in files.items():
        for name in info["defines"]:
            symbol_to_files.setdefault(name, []).append(rel)
    uses = []
    for rel, info in files.items():
        visible = set(info["resolved_imports"])
        for symbol in info["calls"]:
            providers = symbol_to_files.get(symbol, [])
            if len(providers) == 1 and providers[0] != rel:
                uses.append({"src": rel, "dst": providers[0], "symbol": symbol})
            elif visible:
                for provider in providers:
                    if provider in visible and provider != rel:
                        uses.append({"src": rel, "dst": provider, "symbol": symbol})
    import_edges = [{"src": rel, "dst": dst} for rel, info in files.items() for dst in info["resolved_imports"]]
    reverse = {rel: {"imports_by": [], "used_by": []} for rel in files}
    for edge in import_edges:
        reverse[edge["dst"]]["imports_by"].append(edge["src"])
    for edge in uses:
        reverse[edge["dst"]]["used_by"].append(edge["src"])
    for rel in reverse:
        reverse[rel]["imports_by"] = sorted(set(reverse[rel]["imports_by"]))
        reverse[rel]["used_by"] = sorted(set(reverse[rel]["used_by"]))
    graph = {
        "root": str(root),
        "generated_at": now_iso(),
        "files": files,
        "edges": {
            "imports": import_edges,
            "uses": uses,
            "reverse": reverse,
        },
    }
    return graph


def load_graph(path_or_root):
    candidate = Path(path_or_root)
    if candidate.is_file() and candidate.suffix == ".json":
        return json.loads(read_text(candidate))
    return ingest_repository(candidate)


def total_lines(graph):
    return sum(info["lines"] for info in graph["files"].values())


def graph_summary(graph):
    languages = Counter(info["language"] for info in graph["files"].values())
    return {
        "root": graph["root"],
        "file_count": len(graph["files"]),
        "total_lines": total_lines(graph),
        "import_edges": len(graph["edges"]["imports"]),
        "use_edges": len(graph["edges"]["uses"]),
        "languages": dict(sorted(languages.items())),
    }


def normalize_changed(paths, graph):
    root = Path(graph["root"])
    normalized = []
    for raw in paths:
        path = Path(raw)
        if path.is_absolute():
            rel = safe_rel(path, root)
        else:
            rel = str(path).replace("\\", "/")
        if rel not in graph["files"]:
            raise RuntimeError(f"Changed path not found in graph: {raw}")
        normalized.append(rel)
    return sorted(set(normalized))


def reverse_neighbors(graph, node):
    rev = graph["edges"]["reverse"].get(node, {"imports_by": [], "used_by": []})
    return sorted(set(rev["imports_by"] + rev["used_by"]))


def forward_neighbors(graph, node):
    info = graph["files"].get(node, {})
    from_imports = info.get("resolved_imports", [])
    from_uses = [edge["dst"] for edge in graph["edges"]["uses"] if edge["src"] == node]
    return sorted(set(from_imports + from_uses))


def impacted_files(graph, changed_paths):
    queue = deque(changed_paths)
    impacted = set(changed_paths)
    while queue:
        node = queue.popleft()
        for neighbor in reverse_neighbors(graph, node):
            if neighbor not in impacted:
                impacted.add(neighbor)
                queue.append(neighbor)
    return sorted(impacted)


def local_projection(graph, focus_paths, radius=1, max_attrs=48):
    selected = set(focus_paths)
    frontier = set(focus_paths)
    for _ in range(max(radius, 0)):
        nxt = set()
        for node in frontier:
            nxt.update(reverse_neighbors(graph, node))
            nxt.update(forward_neighbors(graph, node))
        nxt -= selected
        selected.update(nxt)
        frontier = nxt
    symbol_reads = Counter()
    symbol_writes = Counter()
    module_reads = Counter()
    for rel in selected:
        info = graph["files"][rel]
        for symbol in info["calls"]:
            symbol_reads[symbol] += 1
        for symbol in info["defines"]:
            symbol_writes[symbol] += 1
        for target in info["resolved_imports"]:
            module_reads[target] += 1
    attrs = []
    for symbol, count in (symbol_reads + symbol_writes).most_common():
        if count > 1:
            attrs.append(("contract:" + symbol, symbol))
    for target, count in module_reads.most_common():
        if count > 0:
            attrs.append(("module:" + target, target))
    attrs = attrs[:max_attrs]
    engine = FCA()
    obj_ids = {}
    attr_ids = {}
    for idx, rel in enumerate(sorted(selected), start=1):
        oid = f"F{idx:03d}"
        obj_ids[rel] = oid
        engine.add_obj(oid, rel)
    for idx, (attr_name, desc) in enumerate(attrs, start=1):
        aid = f"A{idx:03d}"
        attr_ids[attr_name] = aid
        engine.add_attr(aid, attr_name, desc)
    for rel, oid in obj_ids.items():
        for aid in attr_ids.values():
            engine.set_i(oid, aid, "0")
    for rel in sorted(selected):
        oid = obj_ids[rel]
        info = graph["files"][rel]
        for symbol in info["calls"]:
            attr_name = "contract:" + symbol
            if attr_name in attr_ids:
                current = engine.incidence[(oid, attr_ids[attr_name])]
                engine.set_i(oid, attr_ids[attr_name], "R" if current == "0" else "RW")
        for symbol in info["defines"]:
            attr_name = "contract:" + symbol
            if attr_name in attr_ids:
                current = engine.incidence[(oid, attr_ids[attr_name])]
                engine.set_i(oid, attr_ids[attr_name], "W" if current == "0" else "RW")
        for target in info["resolved_imports"]:
            attr_name = "module:" + target
            if attr_name in attr_ids:
                current = engine.incidence[(oid, attr_ids[attr_name])]
                engine.set_i(oid, attr_ids[attr_name], "R" if current == "0" else "RW")
        own_module = "module:" + rel
        if own_module in attr_ids:
            current = engine.incidence[(oid, attr_ids[own_module])]
            engine.set_i(oid, attr_ids[own_module], "W" if current == "0" else "RW")
    engine.compute()
    concepts = []
    for idx, (ext, intn) in enumerate(engine.concepts[:12]):
        concepts.append(
            {
                "index": idx,
                "layer": engine.layers[idx] if idx < len(engine.layers) else 0,
                "files": [engine.objects[o]["name"] for o in sorted(ext)],
                "contracts": [engine.attributes[a]["name"] for a in sorted(intn)],
            }
        )
    return {
        "focus": sorted(focus_paths),
        "selected": sorted(selected),
        "summary": {
            "objects": len(engine.objects),
            "attributes": len(engine.attributes),
            "concepts": len(engine.concepts),
            "rw": engine.rw_count(),
        },
        "concepts": concepts,
    }


def impact_report(graph, changed_paths, radius=1):
    changed = normalize_changed(changed_paths, graph)
    impacted = impacted_files(graph, changed)
    unaffected = sorted(set(graph["files"]) - set(impacted))
    local = local_projection(graph, impacted, radius=radius)
    direct_importers = {path: graph["edges"]["reverse"][path]["imports_by"] for path in changed}
    direct_users = {path: graph["edges"]["reverse"][path]["used_by"] for path in changed}
    return {
        "generated_at": now_iso(),
        "root": graph["root"],
        "changed": changed,
        "impacted": impacted,
        "unaffected_count": len(unaffected),
        "unaffected_sample": unaffected[:30],
        "direct_importers": direct_importers,
        "direct_users": direct_users,
        "local_k": local,
    }


def print_summary(summary):
    print(f"root: {summary['root']}")
    print(f"files: {summary['file_count']}")
    print(f"lines: {summary['total_lines']}")
    print(f"import_edges: {summary['import_edges']}")
    print(f"use_edges: {summary['use_edges']}")
    print("languages:")
    for name, count in summary["languages"].items():
        print(f"  {name}: {count}")


def print_impact(report):
    print("changed:")
    for item in report["changed"]:
        print(f"  - {item}")
    print(f"impacted_count: {len(report['impacted'])}")
    print(f"unaffected_count: {report['unaffected_count']}")
    print("direct_importers:")
    for path, values in report["direct_importers"].items():
        print(f"  {path}: {', '.join(values) or '(none)'}")
    print("direct_users:")
    for path, values in report["direct_users"].items():
        print(f"  {path}: {', '.join(values) or '(none)'}")
    local = report["local_k"]
    print(
        "local_k:"
        f" |G|={local['summary']['objects']}"
        f" |M|={local['summary']['attributes']}"
        f" |B|={local['summary']['concepts']}"
        f" RW={local['summary']['rw']}"
    )
    for concept in local["concepts"][:8]:
        files = ", ".join(concept["files"][:5]) or "empty"
        contracts = ", ".join(concept["contracts"][:5]) or "empty"
        print(f"  C{concept['index']:02d} L{concept['layer']}: [{contracts}] <- [{files}]")


def manifest_prompt(requirements_text, target_lines, target_files=None):
    file_budget_rules = ""
    if target_files:
        file_budget_rules = (
            f"- The entire project must fit within at most {target_files} files.\n"
            f"- Treat {target_files} files as a hard architecture budget, not just a generation limit.\n"
            "- If the budget is small, collapse layers deliberately and produce a compact but complete vertical slice.\n"
            "- Do not plan extra files that will be skipped later.\n"
        )
    return f"""
Design a software project manifest for a sizeable, multi-file codebase.

Requirements:
{requirements_text}

Rules:
- Return pure JSON only.
- Target roughly {target_lines} lines of code across the whole repository.
- Prefer 35-90 files instead of a monolith.
- Include backend, frontend, tests, configuration, and developer tooling when appropriate.
- Every file must have a concrete purpose and realistic approximate line count.
- Use reusable contracts between files.
- Keep internal dependencies acyclic whenever practical.
- For every file, include a verification block that explains how the file should be checked.
{file_budget_rules.rstrip()}

JSON schema:
{{
  "project_name": "snake_case_name",
  "summary": "one paragraph",
  "target_stack": {{
    "frontend": "...",
    "backend": "...",
    "data": "...",
    "infra": "..."
  }},
  "shared_contracts": [
    {{
      "name": "ContractName",
      "kind": "type|api|event|table|service",
      "description": "...",
      "owners": ["path/to/file"],
      "consumers": ["path/to/file"]
    }}
  ],
  "files": [
    {{
      "path": "path/to/file.ext",
      "kind": "source|test|config|doc|script",
      "purpose": "what this file does",
      "depends_on": ["path/to/other/file.ext"],
      "contracts_in": ["ContractA"],
      "contracts_out": ["ContractB"],
      "approx_lines": 120,
      "verification": {{
        "smoke": "python_syntax|config_shape|docker_build_contract|doc_exists|ui_contract",
        "acceptance": ["short executable or inspectable checks"]
      }}
    }}
  ]
}}
"""


def validate_manifest(data, target_files=None):
    if not isinstance(data, dict):
        raise RuntimeError("Manifest must be a JSON object.")
    for key in MANIFEST_SCHEMA:
        if key not in data:
            raise RuntimeError(f"Manifest missing key: {key}")
    if not isinstance(data["files"], list) or not data["files"]:
        raise RuntimeError("Manifest.files must be a non-empty array.")
    seen = set()
    total = 0
    for item in data["files"]:
        for key in ("path", "kind", "purpose", "depends_on", "contracts_in", "contracts_out", "approx_lines"):
            if key not in item:
                raise RuntimeError(f"Manifest file entry missing key: {key}")
        if item["path"] in seen:
            raise RuntimeError(f"Duplicate manifest path: {item['path']}")
        item["verification"] = normalize_verification_block(item)
        seen.add(item["path"])
        total += int(item["approx_lines"])
    if target_files and len(data["files"]) > target_files:
        raise RuntimeError(
            f"Manifest planned {len(data['files'])} files, which exceeds the requested file budget of {target_files}."
        )
    data["approx_total_lines"] = total
    return data


def plan_project(requirements_path, output_path, target_lines, client, target_files=None):
    requirements_text = read_text(requirements_path)
    system = "You are an expert software architect. Output valid JSON only."
    user = manifest_prompt(requirements_text, target_lines, target_files=target_files)
    last_error = None
    for attempt in range(2):
        reply = client.chat(system, user, max_tokens=32000)
        data, err = extract_json(reply)
        if not data:
            last_error = f"Manifest extraction failed: {err}"
            continue
        try:
            data = validate_manifest(data, target_files=target_files)
            break
        except RuntimeError as exc:
            last_error = str(exc)
            if attempt == 0 and target_files:
                user += (
                    "\n\nThe previous answer violated the file budget. "
                    f"Retry with no more than {target_files} files and keep the project complete."
                )
                continue
            raise
    else:
        raise RuntimeError(last_error or "Manifest planning failed.")
    data["generated_at"] = now_iso()
    data["source_requirements"] = str(requirements_path)
    if target_files:
        data["target_files"] = target_files
    write_json(output_path, data)
    return data


def compact_manifest_index(manifest):
    lines = []
    for item in manifest["files"]:
        lines.append(
            f"- {item['path']} | {item['kind']} | {item['approx_lines']} lines | "
            f"depends_on={', '.join(item['depends_on']) or '-'} | "
            f"contracts_in={', '.join(item['contracts_in']) or '-'} | "
            f"contracts_out={', '.join(item['contracts_out']) or '-'} | "
            f"{item['purpose']}"
        )
    return "\n".join(lines)


def format_verification_block(file_spec):
    block = file_spec.get("verification", {})
    acceptance = block.get("acceptance", [])
    acceptance_text = "\n".join(f"  - {item}" for item in acceptance) if acceptance else "  - none"
    return (
        f"smoke: {block.get('smoke', 'exists')}\n"
        f"acceptance:\n{acceptance_text}"
    )


def existing_relative_files(root):
    root = Path(root)
    if not root.exists():
        return set()
    return {
        safe_rel(path, root)
        for path in root.rglob("*")
        if path.is_file()
    }


def python_syntax_errors(root):
    issues = []
    for path, language in repo_files(root):
        if language != "python":
            continue
        text = read_text(path)
        try:
            ast.parse(text)
        except SyntaxError as exc:
            issues.append(
                {
                    "path": safe_rel(path, root),
                    "line": exc.lineno,
                    "message": exc.msg,
                }
            )
    return issues


def unresolved_internal_imports(root, graph):
    root = Path(root).resolve()
    top_level = {p.name.split(".")[0] for p in root.iterdir()} if root.exists() else set()
    issues = []
    for rel, info in graph["files"].items():
        file_path = root / rel
        for spec in info["imports"]:
            if file_path.suffix == ".py":
                internal = spec.startswith(".") or spec.split(".")[0] in top_level
                candidates = python_import_candidates(root, file_path, spec) if internal else []
            else:
                internal = spec.startswith(".")
                candidates = path_like_import_candidates(root, file_path, spec) if internal else []
            if internal and candidates and not any(c.exists() and c.is_file() for c in candidates):
                issues.append(
                    {
                        "path": rel,
                        "import": spec,
                        "candidates": [str(c.relative_to(root)) for c in candidates if str(c).startswith(str(root))],
                    }
                )
    return issues


def sqlalchemy_relationship_issues(root):
    root = Path(root).resolve()
    relationships = []
    class_attrs = {}
    for path, language in repo_files(root):
        if language != "python":
            continue
        text = read_text(path)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        rel = safe_rel(path, root)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = set()
            for stmt in node.body:
                target_name = None
                value = None
                if isinstance(stmt, ast.Assign) and stmt.targets and isinstance(stmt.targets[0], ast.Name):
                    target_name = stmt.targets[0].id
                    value = stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    target_name = stmt.target.id
                    value = stmt.value
                if target_name:
                    attrs.add(target_name)
                if not target_name or not isinstance(value, ast.Call):
                    continue
                func = value.func
                func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if func_name != "relationship":
                    continue
                target_class = None
                if value.args and isinstance(value.args[0], ast.Constant) and isinstance(value.args[0].value, str):
                    target_class = value.args[0].value
                back_populates = None
                for kw in value.keywords:
                    if kw.arg == "back_populates" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        back_populates = kw.value.value
                relationships.append(
                    {
                        "class_name": node.name,
                        "attr_name": target_name,
                        "target_class": target_class,
                        "back_populates": back_populates,
                        "path": rel,
                    }
                )
            class_attrs[node.name] = attrs
    issues = []
    for reln in relationships:
        target = reln["target_class"]
        back = reln["back_populates"]
        if target and back and target in class_attrs and back not in class_attrs[target]:
            issues.append(
                {
                    "path": reln["path"],
                    "class_name": reln["class_name"],
                    "attr_name": reln["attr_name"],
                    "target_class": target,
                    "missing_back_populates": back,
                }
            )
    return issues


def contract_issues(manifest, existing_paths, selected_path_set):
    issues = []
    file_map = manifest_file_map(manifest)
    for item in manifest.get("shared_contracts", []):
        missing_owners = [path for path in item.get("owners", []) if path in selected_path_set and path not in existing_paths]
        missing_consumers = [path for path in item.get("consumers", []) if path in selected_path_set and path not in existing_paths]
        declared_but_unknown = [
            path
            for path in item.get("owners", []) + item.get("consumers", [])
            if path not in file_map
        ]
        if missing_owners or missing_consumers or declared_but_unknown:
            issues.append(
                {
                    "contract": item.get("name"),
                    "missing_owners": missing_owners,
                    "missing_consumers": missing_consumers,
                    "unknown_paths": declared_but_unknown,
                }
            )
    return issues


def verify_project(manifest_path, outdir, max_files=None, require_complete=False):
    manifest = json.loads(read_text(manifest_path))
    validate_manifest(manifest)
    selected_specs = selected_manifest_files(manifest, max_files=max_files)
    selected_path_set = set(item["path"] for item in selected_specs)
    existing_paths = existing_relative_files(outdir)
    missing_files = [path for path in selected_path_set if path not in existing_paths]
    dependency_violations = []
    for file_spec in selected_specs:
        path = file_spec["path"]
        if path not in existing_paths:
            continue
        missing_deps = [dep for dep in internal_manifest_dependencies(file_spec, selected_path_set) if dep not in existing_paths]
        if missing_deps:
            dependency_violations.append({"path": path, "missing_dependencies": missing_deps})
    graph = ingest_repository(outdir) if Path(outdir).exists() else {"root": str(Path(outdir).resolve()), "files": {}, "edges": {"imports": [], "uses": [], "reverse": {}}}
    syntax = python_syntax_errors(outdir)
    unresolved = unresolved_internal_imports(outdir, graph)
    relationship = sqlalchemy_relationship_issues(outdir)
    contracts = contract_issues(manifest, existing_paths, selected_path_set)
    summary = {
        "selected_files": len(selected_specs),
        "generated_files": len(selected_path_set & existing_paths),
        "missing_files": len(missing_files),
        "dependency_violations": len(dependency_violations),
        "syntax_errors": len(syntax),
        "unresolved_internal_imports": len(unresolved),
        "relationship_issues": len(relationship),
        "contract_issues": len(contracts),
    }
    ok = (
        summary["dependency_violations"] == 0
        and summary["syntax_errors"] == 0
        and summary["unresolved_internal_imports"] == 0
        and summary["relationship_issues"] == 0
        and summary["contract_issues"] == 0
        and (not require_complete or summary["missing_files"] == 0)
    )
    return {
        "ok": ok,
        "summary": summary,
        "missing_files": sorted(missing_files),
        "dependency_violations": dependency_violations,
        "syntax_errors": syntax,
        "unresolved_internal_imports": unresolved,
        "relationship_issues": relationship,
        "contract_issues": contracts,
        "graph_summary": graph_summary(graph),
    }


def write_generation_report(report_path, report):
    write_json(report_path, report)


def append_generation_snapshot(report, manifest_path, outdir, max_files, last_file):
    verification = verify_project(manifest_path, outdir, max_files=max_files, require_complete=False)
    actual_total_lines = sum(item["actual_lines"] for item in report["files"])
    report["actual_total_lines"] = actual_total_lines
    report["latest_verification"] = verification
    graph = ingest_repository(outdir) if Path(outdir).exists() else None
    selected_path_set = set(report.get("selected_files", []))
    existing_selected = []
    if graph:
        existing_selected = sorted(path for path in graph["files"] if path in selected_path_set)
    focus = []
    if last_file != "resume" and last_file in existing_selected:
        focus = [last_file]
    elif existing_selected:
        focus = existing_selected[: min(3, len(existing_selected))]
    local_k = None
    if graph and focus:
        local_k = local_projection(graph, focus, radius=1, max_attrs=24)
    report.setdefault("snapshots", []).append(
        {
            "time": now_iso(),
            "last_file": last_file,
            "actual_total_lines": actual_total_lines,
            "summary": verification["summary"],
            "graph_summary": verification["graph_summary"],
            "local_k": local_k,
        }
    )
    return verification


def dependency_context(manifest, generated_files, file_spec, max_chars=12000):
    chunks = []
    for dep in file_spec["depends_on"]:
        if dep in generated_files:
            chunks.append(f"### {dep}\n{generated_files[dep]}")
    joined = "\n\n".join(chunks)
    if len(joined) > max_chars:
        return joined[:max_chars] + "\n\n# truncated"
    return joined


def format_repo_state(verification):
    if not verification:
        return "- no repository state yet"
    summary = verification["summary"]
    graph = verification["graph_summary"]
    return (
        f"- selected_files: {summary['selected_files']}\n"
        f"- generated_files: {summary['generated_files']}\n"
        f"- missing_files: {summary['missing_files']}\n"
        f"- dependency_violations: {summary['dependency_violations']}\n"
        f"- syntax_errors: {summary['syntax_errors']}\n"
        f"- unresolved_internal_imports: {summary['unresolved_internal_imports']}\n"
        f"- relationship_issues: {summary['relationship_issues']}\n"
        f"- contract_issues: {summary['contract_issues']}\n"
        f"- current_repo_files: {graph['file_count']}\n"
        f"- current_repo_lines: {graph['total_lines']}"
    )


def file_prompt(manifest, file_spec, generated_files, verification):
    shared = "\n".join(
        f"- {item['name']} ({item['kind']}): {item['description']}"
        for item in manifest.get("shared_contracts", [])[:60]
    )
    deps = dependency_context(manifest, generated_files, file_spec)
    return f"""
Project: {manifest['project_name']}
Summary:
{manifest['summary']}

Stack:
{json.dumps(manifest.get('target_stack', {}), ensure_ascii=False, indent=2)}

Shared contracts:
{shared or '- none'}

Repository manifest:
{compact_manifest_index(manifest)}

Current file:
- path: {file_spec['path']}
- kind: {file_spec['kind']}
- purpose: {file_spec['purpose']}
- depends_on: {', '.join(file_spec['depends_on']) or '-'}
- contracts_in: {', '.join(file_spec['contracts_in']) or '-'}
- contracts_out: {', '.join(file_spec['contracts_out']) or '-'}
- approximate lines: {file_spec['approx_lines']}
- verification:
{format_verification_block(file_spec)}

Current repository verification state:
{format_repo_state(verification)}

Already generated dependency files:
{deps or '- none'}

Rules:
- Output only the full contents of this single file.
- Keep imports and paths consistent with the manifest.
- Do not import undeclared internal files.
- Assume this file is generated only after its declared internal dependencies are ready.
- This file will be checked for syntax, dependency closure, and internal import closure.
- Do not explain the code.
- Make the file production-like, not toy quality.
"""


def generate_project(manifest_path, outdir, client, max_files=None, progress_callback=None):
    manifest = json.loads(read_text(manifest_path))
    validate_manifest(manifest)
    outdir = Path(outdir)
    ensure_dir(outdir)
    generated_files = {}
    selected_specs = selected_manifest_files(manifest, max_files=max_files)
    selected_path_set = set(item["path"] for item in selected_specs)
    report = {
        "manifest": str(manifest_path),
        "outdir": str(outdir),
        "generated_at": now_iso(),
        "model": client.model,
        "files": [],
        "selected_files": [item["path"] for item in selected_specs],
    }
    report_path = outdir / "konceptos_generation_report.json"
    for file_spec in selected_specs:
        existing = outdir / file_spec["path"]
        if existing.exists():
            generated_files[file_spec["path"]] = existing.read_text(encoding="utf-8", errors="replace")
            report["files"].append(
                {
                    "path": file_spec["path"],
                    "approx_lines": file_spec["approx_lines"],
                    "actual_lines": len(generated_files[file_spec["path"]].splitlines()),
                    "status": "existing",
                }
            )
    latest_verification = append_generation_snapshot(report, manifest_path, outdir, max_files, last_file="resume")
    write_generation_report(report_path, report)
    if progress_callback:
        progress_callback(
            {
                "stage": "resume",
                "report_path": str(report_path),
                "files_recorded": len(report["files"]),
                "latest_verification": latest_verification["summary"],
            }
        )
    pending = [file_spec for file_spec in selected_specs if file_spec["path"] not in generated_files]
    while pending:
        ready_spec = None
        for file_spec in pending:
            deps = internal_manifest_dependencies(file_spec, selected_path_set)
            if all(dep in generated_files for dep in deps):
                ready_spec = file_spec
                break
        if ready_spec is None:
            blocked = [
                {
                    "path": file_spec["path"],
                    "missing_dependencies": [
                        dep for dep in internal_manifest_dependencies(file_spec, selected_path_set) if dep not in generated_files
                    ],
                }
                for file_spec in pending
            ]
            report["blocked"] = blocked
            write_generation_report(report_path, report)
            raise RuntimeError(f"Generation stalled: no dependency-ready files remain. Blocked: {blocked[:10]}")
        file_spec = ready_spec
        pending = [item for item in pending if item["path"] != file_spec["path"]]
        out_path = outdir / file_spec["path"]
        system = "You are a senior software engineer generating one repository file. Output only code."
        user = file_prompt(manifest, file_spec, generated_files, latest_verification)
        step_no = len(report["files"]) + 1
        eprint(f"[{step_no}/{len(selected_specs)}] generate {file_spec['path']}")
        content = client.chat(system, user, max_tokens=32000)
        content = strip_fences(content)
        ensure_dir(out_path.parent)
        out_path.write_text(content, encoding="utf-8")
        generated_files[file_spec["path"]] = content
        report["files"].append(
            {
                "path": file_spec["path"],
                "approx_lines": file_spec["approx_lines"],
                "actual_lines": len(content.splitlines()),
                "status": "generated",
            }
        )
        latest_verification = append_generation_snapshot(report, manifest_path, outdir, max_files, last_file=file_spec["path"])
        write_generation_report(report_path, report)
        if progress_callback:
            progress_callback(
                {
                    "stage": "generated",
                    "file": file_spec["path"],
                    "report_path": str(report_path),
                    "files_recorded": len(report["files"]),
                    "latest_verification": latest_verification["summary"],
                }
            )
    report["actual_total_lines"] = sum(item["actual_lines"] for item in report["files"])
    report["approx_total_lines"] = sum(item["approx_lines"] for item in report["files"])
    report["final_verification"] = verify_project(manifest_path, outdir, max_files=max_files, require_complete=True)
    write_generation_report(report_path, report)
    if progress_callback:
        progress_callback(
            {
                "stage": "final",
                "report_path": str(report_path),
                "files_recorded": len(report["files"]),
                "final_verification": report["final_verification"]["summary"],
            }
        )
    return report


def default_big_project_spec():
    return """# Mario UI Demo

Build a small but complete playable browser demo inspired by Super Mario.

Requirements:

- It should be a simple web game interface, not a full engine-heavy product.
- Include around 5 short levels.
- The player should be able to move, jump, reach a flag, and restart.
- Include a visible HUD with at least level progress and lives or score.
- Keep the scope compact enough for a small demo build.
- Prefer a small complete vertical slice over a large incomplete architecture.

Technical preferences:

- Browser-based.
- Keep the file count small.
- Favor direct playability and visible feedback over backend complexity.
"""


def cmd_ingest(args):
    graph = ingest_repository(args.root)
    summary = graph_summary(graph)
    print_summary(summary)
    if args.output:
        write_json(args.output, graph)
        print(f"wrote: {args.output}")


def cmd_impact(args):
    graph = load_graph(args.source)
    report = impact_report(graph, args.changed, radius=args.radius)
    print_impact(report)
    if args.output:
        write_json(args.output, report)
        print(f"wrote: {args.output}")


def client_from_args(args):
    return OpenRouterClient(api_key=args.api_key, model=args.model)


def cmd_plan(args):
    client = client_from_args(args)
    manifest = plan_project(
        args.requirements,
        args.output,
        args.target_lines,
        client,
        target_files=args.target_files,
    )
    print(f"project_name: {manifest['project_name']}")
    print(f"files: {len(manifest['files'])}")
    print(f"approx_total_lines: {manifest['approx_total_lines']}")
    print(f"wrote: {args.output}")


def cmd_generate(args):
    client = client_from_args(args)
    report = generate_project(args.manifest, args.outdir, client, max_files=args.max_files)
    print(f"model: {client.model}")
    print(f"files_generated: {len(report['files'])}")
    print(f"actual_total_lines: {report['actual_total_lines']}")
    print(f"approx_total_lines: {report['approx_total_lines']}")
    if "final_verification" in report:
        print(f"verification_ok: {report['final_verification']['ok']}")
        print(f"verification_summary: {report['final_verification']['summary']}")
    print(f"report: {Path(args.outdir) / 'konceptos_generation_report.json'}")


def cmd_verify(args):
    verification = verify_project(args.manifest, args.outdir, max_files=args.max_files, require_complete=args.require_complete)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


def cmd_forge(args):
    client = client_from_args(args)
    spec_path = Path(args.requirements)
    if not spec_path.exists():
        spec_path.write_text(default_big_project_spec(), encoding="utf-8")
        print(f"created default requirements: {spec_path}")
    target_files = args.target_files if args.target_files else args.max_files
    manifest = plan_project(
        spec_path,
        args.manifest,
        args.target_lines,
        client,
        target_files=target_files,
    )
    print(f"planned {len(manifest['files'])} files")
    report = generate_project(args.manifest, args.outdir, client, max_files=args.max_files)
    graph = ingest_repository(args.outdir)
    graph_path = Path(args.outdir) / "konceptos_graph.json"
    write_json(graph_path, graph)
    print(f"actual_total_lines: {report['actual_total_lines']}")
    if "final_verification" in report:
        print(f"verification_ok: {report['final_verification']['ok']}")
        print(f"verification_summary: {report['final_verification']['summary']}")
    print(f"graph: {graph_path}")


def build_parser():
    parser = argparse.ArgumentParser(description="KonceptOS 2.0 MVP")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest", help="Ingest a repository into a structural graph")
    ingest.add_argument("root", help="Repository root")
    ingest.add_argument("-o", "--output", help="Write graph JSON")
    ingest.set_defaults(func=cmd_ingest)

    impact = sub.add_parser("impact", help="Run impact analysis from a graph or repo")
    impact.add_argument("source", help="Repository root or graph JSON")
    impact.add_argument("--changed", nargs="+", required=True, help="Changed file paths")
    impact.add_argument("--radius", type=int, default=1, help="Neighborhood radius for local K")
    impact.add_argument("-o", "--output", help="Write report JSON")
    impact.set_defaults(func=cmd_impact)

    plan = sub.add_parser("plan", help="Generate a manifest-first project plan with OpenRouter")
    plan.add_argument("requirements", help="Requirements markdown file")
    plan.add_argument("-o", "--output", required=True, help="Manifest JSON output")
    plan.add_argument("--target-lines", type=int, default=10000, help="Approximate total LOC target")
    plan.add_argument("--target-files", type=int, help="Hard file budget for a complete compact project")
    plan.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model")
    plan.add_argument("--api-key", help="OpenRouter API key. Prefer OPENROUTER_API_KEY.")
    plan.set_defaults(func=cmd_plan)

    generate = sub.add_parser("generate", help="Generate a project from a manifest")
    generate.add_argument("manifest", help="Manifest JSON")
    generate.add_argument("--outdir", required=True, help="Output directory")
    generate.add_argument("--max-files", type=int, help="Generate only the first N files")
    generate.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model")
    generate.add_argument("--api-key", help="OpenRouter API key. Prefer OPENROUTER_API_KEY.")
    generate.set_defaults(func=cmd_generate)

    verify = sub.add_parser("verify", help="Verify a generated project against the manifest")
    verify.add_argument("manifest", help="Manifest JSON")
    verify.add_argument("--outdir", required=True, help="Generated output directory")
    verify.add_argument("--max-files", type=int, help="Verify only the first N manifest files")
    verify.add_argument("--require-complete", action="store_true", help="Fail verification if selected files are missing")
    verify.set_defaults(func=cmd_verify)

    forge = sub.add_parser("forge", help="Plan and generate a large project in one command")
    forge.add_argument("requirements", help="Requirements markdown path")
    forge.add_argument("--manifest", required=True, help="Manifest JSON output path")
    forge.add_argument("--outdir", required=True, help="Output directory")
    forge.add_argument("--target-lines", type=int, default=10000, help="Approximate total LOC target")
    forge.add_argument("--target-files", type=int, help="Hard file budget for a complete compact project")
    forge.add_argument("--max-files", type=int, help="Generate only the first N files")
    forge.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model")
    forge.add_argument("--api-key", help="OpenRouter API key. Prefer OPENROUTER_API_KEY.")
    forge.set_defaults(func=cmd_forge)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as exc:
        eprint(f"ERR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
