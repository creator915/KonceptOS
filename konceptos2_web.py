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
import os
import shlex
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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
JOB_LOCK = threading.Lock()
JOBS = {}
RUN_LOCK = threading.Lock()
RUNNERS = {}


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


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def read_report(outdir):
    report_path = Path(outdir) / "konceptos_generation_report.json"
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8", errors="replace"))


def register_job(kind, payload):
    job_id = uuid.uuid4().hex[:12]
    record = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "payload": payload,
        "result": None,
        "error": None,
        "traceback": None,
    }
    with JOB_LOCK:
        JOBS[job_id] = record
    return record


def update_job(job_id, **updates):
    with JOB_LOCK:
        record = JOBS[job_id]
        record.update(updates)
        record["updated_at"] = now_iso()
        return dict(record)


def get_job(job_id):
    with JOB_LOCK:
        record = JOBS.get(job_id)
        return dict(record) if record else None


def start_background_job(kind, payload, fn):
    record = register_job(kind, payload)

    def runner():
        update_job(record["job_id"], status="running")
        try:
            result = fn()
            update_job(record["job_id"], status="completed", result=result)
        except Exception as exc:
            update_job(
                record["job_id"],
                status="failed",
                error=str(exc),
                traceback=traceback.format_exc(),
            )

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    return record


def register_runner(cwd, command, preview_url):
    run_id = uuid.uuid4().hex[:12]
    record = {
        "run_id": run_id,
        "cwd": str(cwd),
        "command": command,
        "preview_url": preview_url,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "starting",
        "output": [],
        "pid": None,
    }
    with RUN_LOCK:
        RUNNERS[run_id] = record
    return record


def append_runner_output(run_id, line):
    with RUN_LOCK:
        record = RUNNERS[run_id]
        record["output"].append(line.rstrip())
        record["output"] = record["output"][-200:]
        record["updated_at"] = now_iso()


def update_runner(run_id, **updates):
    with RUN_LOCK:
        record = RUNNERS[run_id]
        record.update(updates)
        record["updated_at"] = now_iso()
        return dict(record)


def get_runner(run_id):
    with RUN_LOCK:
        record = RUNNERS.get(run_id)
        return dict(record) if record else None


def start_runner(cwd, command, preview_url=None):
    record = register_runner(cwd, command, preview_url)
    proc = subprocess.Popen(
        command if isinstance(command, str) else shlex.join(command),
        cwd=str(cwd),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    update_runner(record["run_id"], status="running", pid=proc.pid)

    def pump():
        try:
            if proc.stdout:
                for line in proc.stdout:
                    append_runner_output(record["run_id"], line)
            proc.wait()
            status = "completed" if proc.returncode == 0 else "failed"
            update_runner(record["run_id"], status=status, returncode=proc.returncode)
        except Exception as exc:
            append_runner_output(record["run_id"], f"runner error: {exc}")
            update_runner(record["run_id"], status="failed")

    threading.Thread(target=pump, daemon=True).start()
    return record


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
        if parsed.path == "/api/report":
            self.handle_report_query(parsed)
            return
        if parsed.path.startswith("/api/jobs/"):
            self.handle_job_status(parsed.path.split("/")[-1])
            return
        if parsed.path.startswith("/api/runs/"):
            self.handle_run_status(parsed.path.split("/")[-1])
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
            elif parsed.path == "/api/run/start":
                self.handle_run_start(body)
            elif parsed.path == "/api/run/stop":
                self.handle_run_stop(body)
            elif parsed.path == "/api/feedback":
                self.handle_feedback(body)
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

    def normalize_job_result(self, result):
        if not result:
            return None
        outdir = result.get("outdir")
        report = read_report(outdir) if outdir else None
        normalized = dict(result)
        if report:
            normalized["report"] = report
        return normalized

    def handle_report_query(self, parsed):
        params = parse_qs(parsed.query)
        outdir = params.get("outdir", [""])[0]
        if not outdir:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Missing outdir query parameter.")
            return
        report = read_report(coerce_path(outdir))
        if not report:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"No report found for {outdir}")
            return
        self.send_json({"ok": True, "report": report})

    def handle_job_status(self, job_id):
        record = get_job(job_id)
        if not record:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Unknown job: {job_id}")
            return
        result = self.normalize_job_result(record.get("result"))
        payload = dict(record)
        payload["result"] = result
        self.send_json({"ok": True, "job": payload})

    def handle_run_status(self, run_id):
        record = get_runner(run_id)
        if not record:
            self.send_error_json(HTTPStatus.NOT_FOUND, f"Unknown run: {run_id}")
            return
        self.send_json({"ok": True, "run": record})

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
        run_async = bool(body.get("async"))
        payload = {
            "requirements_path": str(req_path),
            "output": str(out_path),
            "target_lines": int(body.get("target_lines", 10000)),
            "model": client.model,
        }
        if run_async:
            job = start_background_job(
                "plan",
                payload,
                lambda: {
                    "manifest_path": str(out_path),
                    "manifest": plan_project(req_path, out_path, int(body.get("target_lines", 10000)), client),
                },
            )
            self.send_json({"ok": True, "job": job})
            return
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
        run_async = bool(body.get("async"))
        payload = {
            "manifest_path": str(manifest_path),
            "outdir": str(outdir),
            "max_files": int(max_files) if max_files else None,
            "model": client.model,
        }
        if run_async:
            job = start_background_job(
                "generate",
                payload,
                lambda: {
                    "outdir": str(outdir),
                    "manifest_path": str(manifest_path),
                    "report": generate_project(manifest_path, outdir, client, max_files=int(max_files) if max_files else None),
                },
            )
            self.send_json({"ok": True, "job": job})
            return
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
        max_files = body.get("max_files")
        run_async = bool(body.get("async"))
        payload = {
            "requirements_path": str(req_path),
            "manifest": str(manifest_path),
            "outdir": str(outdir),
            "target_lines": int(body.get("target_lines", 10000)),
            "max_files": int(max_files) if max_files else None,
            "model": client.model,
        }

        def run_forge():
            manifest = plan_project(req_path, manifest_path, int(body.get("target_lines", 10000)), client)
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
            return {
                "manifest_path": str(manifest_path),
                "outdir": str(outdir),
                "graph_path": str(graph_path),
                "manifest": manifest,
                "generation": generation,
                "verification": verification,
            }

        if run_async:
            job = start_background_job("forge", payload, run_forge)
            self.send_json({"ok": True, "job": job})
            return
        self.send_json({"ok": True, **run_forge()})

    def handle_run_start(self, body):
        cwd = coerce_path(body.get("cwd") or ".")
        command = (body.get("command") or "").strip()
        preview_url = (body.get("preview_url") or "").strip() or None
        if not command:
            raise RuntimeError("Provide a run command.")
        if not cwd.exists():
            raise RuntimeError(f"Run directory not found: {cwd}")
        run = start_runner(cwd, command, preview_url)
        self.send_json({"ok": True, "run": run})

    def handle_run_stop(self, body):
        run_id = (body.get("run_id") or "").strip()
        record = get_runner(run_id)
        if not record:
            raise RuntimeError(f"Unknown run: {run_id}")
        pid = record.get("pid")
        if pid:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
        updated = update_runner(run_id, status="stopped")
        self.send_json({"ok": True, "run": updated})

    def handle_feedback(self, body):
        outdir = coerce_path(body.get("outdir") or ".")
        ensure_parent(outdir / "konceptos_feedback" / "placeholder.txt")
        feedback_text = (body.get("feedback") or "").strip()
        if not feedback_text:
            raise RuntimeError("Provide feedback text.")
        manifest_path = body.get("manifest_path")
        verification = None
        if manifest_path:
            manifest_path = coerce_path(manifest_path)
            if manifest_path.exists():
                verification = verify_project(manifest_path, outdir, require_complete=False)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        feedback_path = outdir / "konceptos_feedback" / f"feedback_{stamp}.md"
        sections = [
            "# User Feedback",
            "",
            f"- time: {now_iso()}",
            f"- outdir: {outdir}",
            "",
            "## Experience Feedback",
            feedback_text,
            "",
        ]
        if verification:
            sections.extend(
                [
                    "## Verification Summary",
                    json.dumps(verification["summary"], ensure_ascii=False, indent=2),
                    "",
                ]
            )
        repair_brief = (
            "You are revising a generated project after user feedback.\n\n"
            f"Output directory: {outdir}\n\n"
            f"User feedback:\n{feedback_text}\n\n"
            f"Verification summary:\n{json.dumps(verification['summary'], ensure_ascii=False, indent=2) if verification else 'none'}\n\n"
            "Return a concrete repair plan: impacted areas, files to modify, and validation steps."
        )
        feedback_path.write_text("\n".join(sections), encoding="utf-8")
        self.send_json(
            {
                "ok": True,
                "feedback_path": str(feedback_path),
                "repair_brief": repair_brief,
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
