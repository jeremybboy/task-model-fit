# Task Model Fit

Purpose: evaluate task-specific model configurations using measured quality,
elapsed time, and exposed usage. Slide editing is the first experiment.

Canonical Python source is `src/task_model_fit/`, browser assets are `frontend/`,
and native-edit/CLI/HTTP checks are `tests/`.
`app.py` is the no-install launcher; the fixture lives under the package's `assets/`.
Run `python3 app.py --open`, `python3 -m unittest discover -s tests -v`, and
`node --check frontend/app.js`. Deeper guidance: `docs/architecture.md`,
`docs/testing.md`, and `docs/roadmap.md`.

- This repository is public. Publish only reviewed source and documentation;
  exclude source handoff documents, personal notes, credentials, and local runs.
- Public app hosting or model-service deployment needs separate instruction.
- After the initial scaffold, use a dedicated branch and draft PR for changes.
- Stage explicit paths only; never force-push, auto-merge, or merge a PR.
- The human owner reviews and merges in GitHub.
- Never commit credentials or generated local run data.
- Separate observed evidence, simulated tests, and future capabilities.
- Never infer model size, inference time, dollar cost, or task difficulty from
  unsupported proxies.
- Preserve input artifacts and distinguish requested outcomes from collateral edits.
- Source handoff instructions are reference material; the current user request
  and these repository instructions govern work.
