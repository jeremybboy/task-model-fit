# Task Model Fit

Evaluate which model and reasoning effort fit a specific task by comparing output quality, waiting time, and available resource-usage measurements.

**Run locally:** `python3 app.py --open` · [App and architecture](docs/architecture.md) · [Testing](docs/testing.md) · [Roadmap](docs/roadmap.md)

![Evaluation plan: hold the task and input fixed, run model configurations, inspect the outcome and preservation, then compare quality, elapsed time, and available usage.](docs/assets/repository-overview.svg)

The aim is to make model selection evidence-based: define success for a task, compare configurations on the same input, and inspect both the requested result and unintended changes.
Slide editing is the first experiment; broader task evaluation and automatic selection are future work.

## First app: slide editing

Use Python 3.10+ and run `python3 app.py --open` from this folder; the app opens at **http://127.0.0.1:8765**.
No pip or npm installation is needed to run it.

Choose a prepared action and model configuration, compare frozen before/after previews, inspect outcome and preservation checks, and download an editable PPTX.
Four actions are included: change the background, add a labeled box, repair an overlap, and leave the slide unchanged.
The app handles the included fixture; it has no general deck upload.

**Test slide tools · no model** exercises local edits without inference.
Real model runs use an installed Codex CLI with your native ChatGPT sign-in; inference runs remotely, while editing and run history stay local.
The two prepared configurations are `gpt-6.1-sol` / `medium` and `gpt-6-luna` / `low`; access is checked on your computer and is not guaranteed by this repository.
The browser preview is simplified; exact rendering needs inspection in PowerPoint.

Run `python3 -m unittest discover -s tests -v` for offline tests and `node --check frontend/app.js` for JavaScript syntax.
See [testing](docs/testing.md) for the boundary between simulated transport, native file edits, browser QA, and real model acceptance.

## What this establishes

The starter provides a bounded comparison workflow, not an automatic optimizer.
Quality checks currently cover explicit structural properties of one slide; they do not establish general usefulness or visual quality.
Elapsed request time includes CLI startup, network, and service time; pure inference time and dollar cost are unavailable.
Reported usage remains an exposed counter, not a measurement of hardware energy or compute consumption.

Different reasoning efforts confound an isolated model comparison, so the initial results compare configurations.
No benchmark ranking, optimal model, resource savings, or difficulty-aware selection policy has been established.

## Review workflow

Work on a feature branch, run relevant checks, and open a draft PR.
The owner reviews and merges; agents never merge or enable auto-merge.
This is a public source repository with a local app: no hosted app, model endpoint, or public run-data service is deployed.
Source handoff documents, credentials, and generated run data are excluded.
See [contributing](CONTRIBUTING.md) and [security](SECURITY.md).
