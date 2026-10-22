# Local app and experiment boundary

The browser at `http://127.0.0.1:8765` talks to a Python HTTP server bound to
loopback. The server calls a locally installed Codex CLI for structured edit
operations and applies them through the same allowlisted native PPTX tools for
every configuration. Model inference is remote. Deterministic tool tests skip it.

## Current source

- `app.py`: launches the app from a checkout without installation.
- `src/task_model_fit/app.py`: localhost routes, run lifecycle, snapshots, and history.
- `src/task_model_fit/codex_bridge.py`: CLI authentication status, structured plans,
  exact model/effort arguments, error classification, and exposed usage.
- `src/task_model_fit/slide_tools.py`: fixture inspection, bounded edits,
  simplified SVG preview, and structural audits.
- `src/task_model_fit/assets/baseline.pptx`: the single editable test fixture.
- `frontend/`: browser controls, before/after comparison, measurements, and replay.
- `tests/`: native file, simulated CLI, and HTTP tests with temporary run data.

No browser build system or Python runtime dependency is required.
Local history and outputs live in `.slide-lab-data/` and are Git-ignored.
Use `--port 8766` to change the port or `--codex /path/to/codex` to select an executable.

## Comparison behavior

The baseline stays fixed when comparing another model on the same action.
Selecting another action uses the last completed result as its baseline.
Reset restores the original fixture. The right preview follows saved files;
replay follows recorded timing and makes no new request.

Custom instructions use the same CLI adapter and operation allowlist as presets.
Each instruction is a single run, with the model's edit summary shown beneath the
text field. Instructions are trimmed, limited to 1,500 characters, recorded in
local run history, and included in the structured request. Blank/invalid input
is rejected before launching the CLI; deterministic tool tests accept presets only.
This is an instruction/reply interface, not a conversation with previous chat turns.

Repeating the same custom instruction with another model keeps the input fixed.
Changing its wording after a completed run uses that completed result as the new
baseline. History comparison matches the baseline and exact normalized instruction.
Reset restores the original fixture without deleting run history.

Custom audits check dimensions, existing text/sizes/styles, and shape bounds.
They cannot determine whether arbitrary wording was fulfilled, so the outcome
requires human review even when those structural checks pass.

The model receives structured text and geometry, not a slide image.
The app requests operations rather than desktop automation. A plan is applied
only after successful CLI completion, exit code zero, and local validation.
The CLI is requested to use a read-only sandbox; unexpected reported tool use
rejects the response. This is not a claim that all possible tool access is disabled.

## Planned generalization

Task adapters would define inputs, allowed operations, success and preservation
criteria, and reviewable outputs. Shared run records would distinguish requested
configuration, observed settings, wall time, available usage, checks, and errors.
Neither that generalized adapter interface nor an automatic selection policy
exists yet. The slide implementation is the concrete first experiment.
