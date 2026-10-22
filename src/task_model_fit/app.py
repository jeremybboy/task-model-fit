#!/usr/bin/env python3
"""Task Model Fit: a local slide experiment. Python 3.10+, no pip dependencies."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
from urllib.parse import urlparse
import uuid
import webbrowser

from . import codex_bridge as codex
from . import slide_tools as slides

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
TASKS = {
    "background": {"label": "Change background to gray", "prompt": "Change only the slide background to gray #4A5054. Preserve all shapes and text."},
    "box": {"label": "Add a Next step box", "prompt": "Add one mint #A7F3D0 rectangle in the bottom-right corner, labeled exactly Next step. Keep existing objects unchanged."},
    "overlap": {"label": "Move the square clear of text", "prompt": "Move accent-square so it no longer overlaps any text box. Preserve its size, color and all other slide content."},
    "unchanged": {"label": "Leave the slide unchanged", "prompt": "Keep this slide exactly as it is. Make no changes."},
}


class Lab:
    def __init__(self, data_dir, binary=None):
        self.data = Path(data_dir).resolve()
        self.snapshots = self.data / "snapshots"
        self.runs_dir = self.data / "runs"
        self.snapshots.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.binary = binary
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.active = None
        self.runs = {}
        self.cancels = {}
        self.original = self.snapshot(ROOT / "assets/baseline.pptx")
        for path in sorted(self.runs_dir.glob("*/run.json"))[-100:]:
            try:
                run = json.loads(path.read_text())
                if run.get("status") == "running":
                    run.update(status="interrupted", error="The previous app process stopped during this run.")
                self.runs[run["id"]] = run
            except (ValueError, KeyError, OSError):
                continue

    def snapshot(self, path):
        key = slides.digest(path)
        destination = self.snapshots / (key + ".pptx")
        if not destination.exists():
            shutil.copyfile(path, destination)
        svg = self.snapshots / (key + ".svg")
        if not svg.exists():
            svg.write_text(slides.render_svg(slides.inspect(destination)), encoding="utf-8")
        return key

    def state(self, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key) or not (self.snapshots / (key + ".pptx")).is_file():
            raise ValueError("Unknown slide baseline.")
        return {"id": key, "preview": f"/files/snapshots/{key}.svg", "pptx": f"/files/snapshots/{key}.pptx",
                "slide": slides.inspect(self.snapshots / (key + ".pptx"))}

    def get_run(self, key):
        with self.lock:
            if key not in self.runs:
                raise ValueError("Unknown run.")
            result = copy.deepcopy(self.runs[key])
            if self.active == key and result["status"] != "running":
                result["status"] = "running"
            return result

    def history(self):
        with self.lock:
            return sorted((copy.deepcopy(run) for run in self.runs.values()), key=lambda r: r["created_utc"], reverse=True)[:100]

    def start(self, task, model, baseline, mode):
        started = time.monotonic()
        if task not in TASKS or model not in codex.MODELS or mode not in ("live", "tools"):
            raise ValueError("Choose an available task and model.")
        self.state(baseline)
        if mode == "live":
            status = codex.connection(self.binary)
            if not status["ready"]:
                raise ValueError(status["message"])
        with self.lock:
            if self.active:
                raise ValueError("A run is already in progress.")
            key = uuid.uuid4().hex
            self.active = key
            self.cancels[key] = threading.Event()
            self.runs[key] = {
                "id": key, "created_utc": datetime.now(timezone.utc).isoformat(),
                "task": task, "task_label": TASKS[task]["label"], "mode": mode,
                "model": model if mode == "live" else None,
                "effort": codex.MODELS[model]["effort"] if mode == "live" else None,
                "status": "running", "baseline": baseline, "after": baseline,
                "events": [], "steps": [], "metrics": {}, "audit": None,
                "preview_kind": "Simplified preview of native PPTX text and rectangles",
            }
            (self.runs_dir / key).mkdir()
            threading.Thread(target=self.perform, args=(key, model, started), daemon=True).start()
            return key

    def perform(self, key, model, started):
        directory = self.runs_dir / key
        run = self.runs[key]
        cancel = self.cancels[key]

        def emit(kind, label, **extra):
            with self.lock:
                run["events"].append({"type": kind, "label": label,
                    "received_seconds": round(time.monotonic() - started, 4), **extra})

        try:
            source = self.snapshots / (run["baseline"] + ".pptx")
            before = slides.inspect(source)
            shutil.copyfile(source, directory / "before.pptx")
            emit("run.started", "Run started" if run["mode"] == "live" else "Slide-tool test started · no model")
            if run["mode"] == "live":
                emit("model.started", f"Requesting {codex.MODELS[model]['label']} · {codex.MODELS[model]['effort']}")
                plan, metrics = codex.request(codex.executable(self.binary), TASKS[run["task"]]["prompt"], before,
                    directory, emit, cancel, model=model)
                with self.lock:
                    run["metrics"].update(metrics)
                emit("model.completed", "Structured edit received")
            else:
                plan = slides.tool_test_plan(run["task"], before)
                run["metrics"].update(elapsed_request_seconds=None, usage=None)
            (directory / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
            with self.lock:
                run["note"] = plan["note"]
            apply_seconds = render_seconds = 0
            for index, operation in enumerate(plan["operations"], 1):
                if cancel.is_set():
                    raise codex.ModelError("cancelled")
                emit("tool.started", "Applying " + operation["op"])
                destination = directory / f"step-{index:02d}.pptx"
                timer = time.monotonic()
                slides.apply(source, destination, operation)
                apply_seconds += time.monotonic() - timer
                emit("tool.completed", "PowerPoint file saved")
                timer = time.monotonic()
                snapshot = self.snapshot(destination)
                render_seconds += time.monotonic() - timer
                step = {"state": snapshot, "operation": operation["op"], "received_seconds": round(time.monotonic() - started, 4)}
                with self.lock:
                    run["steps"].append(step)
                    run["after"] = snapshot
                emit("render.completed", "Slide preview updated", state=snapshot)
                source = destination
            shutil.copyfile(source, directory / "after.pptx")
            timer = time.monotonic()
            outcome = slides.audit(before, slides.inspect(source), run["task"])
            audit_seconds = time.monotonic() - timer
            with self.lock:
                run["audit"] = outcome
                run["status"] = "completed"
                run["metrics"].update(apply_save_seconds=round(apply_seconds, 4), render_seconds=round(render_seconds, 4),
                    audit_seconds=round(audit_seconds, 4), total_action_seconds=round(time.monotonic() - started, 4),
                    first_rendered_edit_seconds=next((s["received_seconds"] for s in run["steps"] if s["state"] != run["baseline"]), None))
            emit("audit.completed", "Checks passed" if outcome["passed"] else "Review required: a check failed")
        except codex.ModelError as error:
            with self.lock:
                run["metrics"].update(error.metrics)
                run.update(status="cancelled" if error.category == "cancelled" else "failed", error=str(error), error_category=error.category)
            emit("run.failed", str(error))
        except (ValueError, OSError, KeyError) as error:
            with self.lock:
                run.update(status="failed", error="The proposed operation could not be applied: " + str(error)[:300])
            emit("run.failed", run["error"])
        except Exception:
            with self.lock:
                run.update(status="failed", error="An unexpected local error occurred. Inspect the app in local Codex.")
            emit("run.failed", run["error"])
        finally:
            with self.lock:
                run["metrics"].setdefault("total_action_seconds", round(time.monotonic() - started, 4))
                (directory / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
                self.active = None


class Handler(BaseHTTPRequestHandler):
    server_version = "SlideLab/0.1"

    @property
    def lab(self):
        return self.server.lab

    def log_message(self, *_):
        pass

    def send(self, payload, content_type="application/json", status=200):
        data = payload if isinstance(payload, bytes) else (json.dumps(payload).encode() if content_type == "application/json" else payload.encode())
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self, api=False):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self.send({"error": "Local access only."}, status=403)
            return False
        if api and not secrets.compare_digest(self.headers.get("X-Slide-Lab-Token", ""), self.lab.token):
            self.send({"error": "Reload the app page to reconnect."}, status=403)
            return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if not self.allowed(api=path.startswith("/api/")):
            return
        try:
            if path in ("/", "/app.js", "/style.css"):
                name = "index.html" if path == "/" else path[1:]
                text = (PROJECT_ROOT / "frontend" / name).read_text().replace("__SESSION_TOKEN__", self.lab.token)
                self.send(text, {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript", "style.css": "text/css"}[name])
            elif path == "/api/bootstrap":
                self.send({"original": self.lab.state(self.lab.original), "tasks": TASKS, "models": codex.MODELS})
            elif path == "/api/connection":
                self.send(codex.connection(self.lab.binary))
            elif path == "/api/runs":
                self.send(self.lab.history())
            elif re.fullmatch(r"/api/runs/[a-f0-9]{32}", path):
                self.send(self.lab.get_run(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/api/states/[a-f0-9]{64}", path):
                self.send(self.lab.state(path.rsplit("/", 1)[1]))
            elif re.fullmatch(r"/files/snapshots/[a-f0-9]{64}\.(pptx|svg)", path):
                filename = self.lab.snapshots / path.rsplit("/", 1)[1]
                self.send(filename.read_bytes(), "image/svg+xml" if filename.suffix == ".svg" else "application/vnd.openxmlformats-officedocument.presentationml.presentation")
            else:
                self.send({"error": "Not found."}, status=404)
        except (ValueError, OSError):
            self.send({"error": "Not found."}, status=404)

    def do_POST(self):
        if not self.allowed(api=True):
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 4096:
                raise ValueError("Request too large.")
            data = json.loads(self.rfile.read(size))
            if self.path == "/api/run":
                key = self.lab.start(data["task"], data["model"], data["baseline"], data["mode"])
                self.send({"id": key}, status=202)
            elif self.path == "/api/cancel":
                if data.get("id") in self.lab.cancels:
                    self.lab.cancels[data["id"]].set()
                self.send({"ok": True})
            else:
                self.send({"error": "Not found."}, status=404)
        except (ValueError, KeyError) as error:
            self.send({"error": str(error)[:300]}, status=400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--codex", help="Optional path to the installed Codex executable")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / ".slide-lab-data")
    parser.add_argument("--open", action="store_true", help="Open the app in the default browser")
    args = parser.parse_args()
    lab = Lab(args.data_dir, args.codex)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.lab = lab
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Task Model Fit is running: {url}", flush=True)
    print("Run model = real Codex request. Test slide tools = local file edits with no model. Ctrl+C stops the app.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        for event in lab.cancels.values():
            event.set()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
