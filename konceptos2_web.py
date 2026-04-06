#!/usr/bin/env python3
"""
KonceptOS 2.0 MVP Web UI

Local no-dependency web server for:
- repository ingest
- impact analysis
- manifest planning
- project generation
"""

import argparse
import json
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from konceptos2_mvp import (
    OpenRouterClient,
    default_big_project_spec,
    generate_project,
    graph_summary,
    impact_report,
    ingest_repository,
    load_graph,
    plan_project,
    verify_project,
)


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "webui"


def ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def coerce_path(raw):
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw) if raw else {}


class KonceptOSWebServer(ThreadingHTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "KonceptOS2Web/0.1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "service": "KonceptOS 2.0 MVP Web",
                    "default_model": self.server.default_model,
                }
            )
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = read_json_body(self)
            if parsed.path == "/api/ingest":
                self.handle_ingest(body)
            elif parsed.path == "/api/impact":
                self.handle_impact(body)
            elif parsed.path == "/api/plan":
                self.handle_plan(body)
            elif parsed.path == "/api/generate":
                self.handle_generate(body)
            elif parsed.path == "/api/verify":
                self.handle_verify(body)
            elif parsed.path == "/api/forge":
                self.handle_forge(body)
            elif parsed.path == "/api/default-spec":
                self.send_json({"ok": True, "requirements_text": default_big_project_spec()})
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, f"Unknown endpoint: {parsed.path}")
        except json.JSONDecodeError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {exc}")
        except RuntimeError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(exc).__name__}: {exc}")

    def log_message(self, format_, *args):
        return

    def serve_static(self, path):
        target = "index.html" if path in ("", "/") else path.lstrip("/")
        file_path = (WEB_ROOT / target).resolve()
        if not str(file_path).startswith(str(WEB_ROOT.resolve())) or not file_path.exists() or not file_path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Static asset not found: {path}")
            return
        suffix = file_path.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(suffix, "text/plain; charset=utf-8")
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, payload, status=HTTPStatus.OK):
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_error_json(self, status, message):
        self.send_json({"ok": False, "error": message}, status=status)

    def build_client(self, body):
        return OpenRouterClient(api_key=body.get("api_key"), model=body.get("model") or self.server.default_model)

    def resolve_requirements_path(self, body):
        req_text = (body.get("requirements_text") or "").strip()
        req_path = (body.get("requirements_path") or "").strip()
        if req_text:
            temp = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
            with temp:
                temp.write(req_text)
            return Path(temp.name)
        if req_path:
            path = coerce_path(req_path)
            if not path.exists():
                raise RuntimeError(f"Requirements file not found: {path}")
            return path
        raise RuntimeError("Provide requirements_text or requirements_path.")

    def handle_ingest(self, body):
        root = coerce_path(body.get("root") or ".")
        graph = ingest_repository(root)
        result = {
            "ok": True,
            "root": str(root),
            "summary": graph_summary(graph),
        }
        out = (body.get("output") or "").strip()
        if out:
            out_path = coerce_path(out)
            ensure_parent(out_path)
            out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
            result["graph_path"] = str(out_path)
        else:
            result["graph"] = graph
        self.send_json(result)

    def handle_impact(self, body):
        source = (body.get("source") or ".").strip()
        changed = body.get("changed") or []
        if isinstance(changed, str):
            changed = [line.strip() for line in changed.splitlines() if line.strip()]
        if not changed:
            raise RuntimeError("Provide at least one changed file.")
        graph = load_graph(coerce_path(source))
        report = impact_report(graph, changed, radius=int(body.get("radius", 1)))
        result = {"ok": True, "report": report}
        out = (body.get("output") or "").strip()
        if out:
            out_path = coerce_path(out)
            ensure_parent(out_path)
            out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            result["report_path"] = str(out_path)
        self.send_json(result)

    def handle_plan(self, body):
        client = self.build_client(body)
        req_path = self.resolve_requirements_path(body)
        out_path = coerce_path(body.get("output") or "big_project_manifest.json")
        ensure_parent(out_path)
        manifest = plan_project(req_path, out_path, int(body.get("target_lines", 10000)), client)
        self.send_json({"ok": True, "manifest_path": str(out_path), "manifest": manifest})

    def handle_generate(self, body):
        client = self.build_client(body)
        manifest_path = coerce_path(body.get("manifest_path") or "")
        if not manifest_path.exists():
            raise RuntimeError(f"Manifest file not found: {manifest_path}")
        outdir = coerce_path(body.get("outdir") or "generated_big_project")
        outdir.mkdir(parents=True, exist_ok=True)
        max_files = body.get("max_files")
        report = generate_project(manifest_path, outdir, client, max_files=int(max_files) if max_files else None)
        self.send_json({"ok": True, "outdir": str(outdir), "report": report})

    def handle_verify(self, body):
        manifest_path = coerce_path(body.get("manifest_path") or "")
        if not manifest_path.exists():
            raise RuntimeError(f"Manifest file not found: {manifest_path}")
        outdir = coerce_path(body.get("outdir") or "generated_big_project")
        max_files = body.get("max_files")
        verification = verify_project(
            manifest_path,
            outdir,
            max_files=int(max_files) if max_files else None,
            require_complete=bool(body.get("require_complete")),
        )
        self.send_json({"ok": True, "outdir": str(outdir), "verification": verification})

    def handle_forge(self, body):
        client = self.build_client(body)
        req_path = self.resolve_requirements_path(body)
        manifest_path = coerce_path(body.get("manifest") or "big_project_manifest.json")
        outdir = coerce_path(body.get("outdir") or "generated_big_project")
        ensure_parent(manifest_path)
        outdir.mkdir(parents=True, exist_ok=True)
        manifest = plan_project(req_path, manifest_path, int(body.get("target_lines", 10000)), client)
        max_files = body.get("max_files")
        generation = generate_project(manifest_path, outdir, client, max_files=int(max_files) if max_files else None)
        graph = ingest_repository(outdir)
        graph_path = outdir / "konceptos_graph.json"
        graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        verification = verify_project(
            manifest_path,
            outdir,
            max_files=int(max_files) if max_files else None,
            require_complete=False,
        )
        self.send_json(
            {
                "ok": True,
                "manifest_path": str(manifest_path),
                "outdir": str(outdir),
                "graph_path": str(graph_path),
                "manifest": manifest,
                "generation": generation,
                "verification": verification,
            }
        )


def main():
    parser = argparse.ArgumentParser(description="KonceptOS 2.0 MVP Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument(
        "--model",
        default="anthropic/claude-opus-4.6",
        help="Default OpenRouter model shown in the UI",
    )
    args = parser.parse_args()

    server = KonceptOSWebServer((args.host, args.port), Handler)
    server.default_model = args.model
    print(f"KonceptOS 2.0 MVP Web UI on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
