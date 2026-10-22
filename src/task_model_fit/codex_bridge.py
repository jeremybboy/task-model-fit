"""Local Codex subprocess adapter. Uses native ChatGPT sign-in, never reads auth files."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time

MODEL = "gpt-6.1-sol"
EFFORT = "medium"
MODELS = {
    "gpt-6-luna": {"label": "GPT-6 Luna", "effort": "low"},
    "gpt-6.1-sol": {"label": "GPT-6.1 Sol", "effort": "medium"},
}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "operations": {"type": "array", "minItems": 1, "maxItems": 6,
            "items": {"type": "object", "additionalProperties": False,
                "properties": {
                    "op": {"type": "string", "enum": ["set_background", "add_box", "move_shape", "no_change"]},
                    "shape_id": {"type": ["string", "null"]},
                    **{key: {"type": ["number", "null"]} for key in ("x", "y", "width", "height")},
                    "color": {"type": ["string", "null"]},
                    "text": {"type": ["string", "null"]},
                },
                "required": ["op", "shape_id", "x", "y", "width", "height", "color", "text"],
            }},
        "note": {"type": "string"},
    },
    "required": ["operations", "note"],
}


def environment():
    env = dict(os.environ)
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        env.pop(name, None)
    return env


def classify(message):
    s = message.lower()
    for category, terms in (
        ("host_runtime_unsupported", ("no /proc/self/exe",)),
        ("rate_or_usage_limit", ("429", "rate limit", "usage limit", "quota")),
        ("model_unavailable", ("not supported", "unsupported", "model not found", "invalid model")),
        ("authentication_or_access", ("not logged in", "unauthorized", "401", "403", "access denied")),
        ("network_or_certificate", ("certificate", "tls", "connection", "network", "dns")),
        ("local_configuration", ("configuration", "config.toml", "permission denied")),
    ):
        if any(term in s for term in terms):
            return category
    return "codex_request_failed"


MESSAGES = {
    "host_runtime_unsupported": "This runtime cannot start Codex. Run Slide lab on your laptop where Codex already works.",
    "model_unavailable": "The selected model or effort was rejected. Inspect /model in native Codex.",
    "authentication_or_access": "Codex sign-in or model access needs attention. Run codex login status in Terminal.",
    "rate_or_usage_limit": "Codex reported a usage or rate limit.",
    "network_or_certificate": "Codex could not complete the network connection. Check the native CLI on this computer.",
    "local_configuration": "Codex could not load its local configuration. Check the native CLI.",
    "codex_request_failed": "Codex did not complete a usable response. Run the equivalent command in Terminal for diagnostics.",
}


class ModelError(RuntimeError):
    def __init__(self, category, metrics=None):
        super().__init__(MESSAGES.get(category, category.replace("_", " ")))
        self.category = category
        self.metrics = metrics or {}


def executable(override=None):
    if override:
        return shutil.which(override) or str(Path(override).expanduser().resolve())
    found = shutil.which("codex")
    standard = Path.home() / ".local/bin/codex"
    return found or (str(standard) if standard.is_file() else None)


def connection(override=None):
    binary = executable(override)
    result = {"ready": False, "model": MODEL, "effort": EFFORT,
              "authentication": "unknown", "version": None,
              "model_access": "untested_on_this_app", "workspace": "Confirm in native Codex"}
    if not binary:
        return dict(result, category="cli_missing", message="Codex CLI was not found. Install it or start with --codex /path/to/codex.")
    try:
        version = subprocess.run([binary, "--version"], env=environment(), capture_output=True,
                                 text=True, errors="replace", timeout=15)
        match = re.search(r"codex(?:-cli)?\s+v?([0-9]+\.[0-9]+\.[0-9]+)", version.stdout)
        result["version"] = match.group(1) if match else None
        auth = subprocess.run([binary, "login", "status"], env=environment(), capture_output=True,
                              text=True, errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return dict(result, category="cli_start_failed", message="Codex could not start. Check codex --version in Terminal.")
    message = auth.stdout + "\n" + auth.stderr
    if auth.returncode:
        category = classify(message)
        return dict(result, category=category, message=MESSAGES[category])
    if any(word in message.lower() for word in ("api key", "api_key", "api-key")):
        return dict(result, authentication="api_key", category="wrong_authentication",
                    message="Codex is using an API key. This app expects your existing ChatGPT sign-in.")
    if "chatgpt" not in message.lower():
        return dict(result, category="authentication_unknown", message="ChatGPT sign-in could not be confirmed. Check codex login status.")
    return dict(result, ready=True, authentication="chatgpt", category="signed_in",
                message="ChatGPT sign-in detected. Run an edit to test the model through this app.")


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {"operations", "note"}:
        raise ModelError("invalid_structured_response")
    operations = plan["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 6 or not isinstance(plan["note"], str) or len(plan["note"]) > 1500:
        raise ModelError("invalid_structured_response")
    keys = {"op", "shape_id", "x", "y", "width", "height", "color", "text"}
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != keys or operation["op"] not in ("set_background", "add_box", "move_shape", "no_change"):
            raise ModelError("invalid_structured_response")
        for key in ("shape_id", "color", "text"):
            if operation[key] is not None and not isinstance(operation[key], str):
                raise ModelError("invalid_structured_response")
        for key in ("x", "y", "width", "height"):
            if operation[key] is not None and (isinstance(operation[key], bool) or not isinstance(operation[key], (float, int))):
                raise ModelError("invalid_structured_response")
    return plan


def request(binary, task_prompt, state, directory, emit, cancel, timeout=180, model=MODEL):
    if model not in MODELS:
        raise ModelError("model_unavailable")
    effort = MODELS[model]["effort"]
    directory = Path(directory)
    schema = directory / "output-schema.json"
    schema.write_text(json.dumps(SCHEMA), encoding="utf-8")
    prompt = (
        "You select operations for a bounded PowerPoint editing app. Do not read files, run commands, "
        "browse, call tools, or change any files yourself. Return only JSON matching the output schema. "
        "The app will apply your operations using fixed local tools. Coordinates are slide pixels, "
        "origin at top-left. Keep every shape inside the slide. Preserve everything unrelated to the request. "
        "Use null for operation fields that do not apply. Colors use #RRGGBB. "
        "For move_shape use an exact existing shape id. For add_box use a readable size and explicit text. "
        "Use no_change when no modification is needed. Return a brief note describing your action.\n"
        "REQUEST: " + task_prompt + "\nCURRENT_SLIDE: " + json.dumps(state, ensure_ascii=False)
    )
    args = [binary, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
            "--model", model, "-c", f'model_reasoning_effort="{effort}"', "-c", 'model_provider="openai"',
            "--output-schema", str(schema.resolve()), prompt]
    started = time.monotonic()
    metrics = {"requested_model": model, "requested_effort": effort,
               "effective_model": None, "effective_effort": None,
               "elapsed_request_seconds": None, "provider_compute_seconds": None,
               "first_cli_event_seconds": None, "usage": None, "cli_returncode": None,
               "note": "Elapsed request includes CLI startup, network and service overhead."}
    try:
        process = subprocess.Popen(args, cwd=directory, env=environment(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   errors="replace", bufsize=1)
    except OSError:
        raise ModelError("codex_request_failed", metrics)
    messages = queue.Queue()

    def read(pipe, source):
        try:
            for line in pipe:
                messages.put((source, line, time.monotonic() - started))
        finally:
            pipe.close()
            messages.put((source, None, time.monotonic() - started))

    for pipe, source in ((process.stdout, "stdout"), (process.stderr, "stderr")):
        threading.Thread(target=read, args=(pipe, source), daemon=True).start()
    done, diagnostics, final, completed, failed, tools_used = set(), [], None, False, False, False
    reason = None
    while len(done) < 2:
        if cancel.is_set() or time.monotonic() - started > timeout:
            reason = "cancelled" if cancel.is_set() else "request_timeout"
            process.kill()
            break
        try:
            source, line, offset = messages.get(timeout=.1)
        except queue.Empty:
            continue
        if line is None:
            done.add(source)
            continue
        if source == "stderr":
            if sum(map(len, diagnostics)) < 64000:
                diagnostics.append(line)
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            continue
        kind = event["type"]
        if metrics["first_cli_event_seconds"] is None:
            metrics["first_cli_event_seconds"] = round(offset, 4)
        if re.fullmatch(r"[a-z_.-]{1,60}", kind):
            emit("model.event", "Codex · " + kind, cli_event=kind, request_offset_seconds=round(offset, 4))
        item = event.get("item", {})
        if isinstance(item, dict):
            tools_used |= item.get("type") in ("command_execution", "mcp_tool_call", "web_search", "file_change")
            if kind == "item.completed" and item.get("type") == "agent_message":
                final = item.get("text")
        if kind == "turn.completed":
            completed = True
            usage = event.get("usage", {})
            if isinstance(usage, dict):
                metrics["usage"] = {k: v for k, v in usage.items() if k in (
                    "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "reasoning_tokens")
                    and type(v) is int and v >= 0}
        if kind in ("error", "turn.failed"):
            failed = True
            diagnostics.append(json.dumps(event)[:8000])
    try:
        code = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        code = process.wait()
    metrics["elapsed_request_seconds"] = round(time.monotonic() - started, 4)
    metrics["cli_returncode"] = code
    diagnostics_text = "\n".join(diagnostics)
    if reason:
        raise ModelError(reason, metrics)
    if code or failed or not completed:
        raise ModelError(classify(diagnostics_text), metrics)
    if tools_used:
        raise ModelError("unexpected_model_tool_use", metrics)
    try:
        plan = validate_plan(json.loads(final))
    except ModelError as error:
        error.metrics = metrics
        raise
    except (ValueError, TypeError):
        raise ModelError("invalid_structured_response", metrics)
    if "codex_memories_write" in diagnostics_text:
        metrics["cli_warning"] = "Codex emitted a memory-writer diagnostic; the requested turn completed and the CLI exited successfully."
    return plan, metrics
