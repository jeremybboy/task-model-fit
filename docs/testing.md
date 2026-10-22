# Testing and evidence

## Offline checks

```bash
python3 -m unittest discover -s tests -v
node --check frontend/app.js
```

The eleven tests exercise real PPTX editing and preservation, invalid operations
and geometry, deliberately simulated CLI authentication/responses/errors,
exact model/effort arguments, selected credential-environment isolation,
run recording, and the localhost HTTP/download path. Custom coverage includes
UTF-8 instruction transport through HTTP and the simulated CLI, a native yellow
square/text edit, run-history persistence, rejection before CLI startup, and
structural checks that never certify arbitrary instruction fulfillment.
No real model request runs
in this suite. CI runs these checks on Python 3.10 and 3.14.

On October 22, 2026, all eleven tests and JavaScript syntax validation passed on
this Mac after adding custom instructions. The local
HTTP test required permission to bind a temporary loopback port. Python 3.14
emitted a non-fatal resource-cleanup warning for the expected HTTP 403 test.

## Browser checks

Launch `python3 app.py --open`. At 1440- and 1280-pixel desktop widths and a narrow
mobile width, check controls, keyboard focus, before/after panes, and readable
measurements. Run the no-model tool check, download the PPTX, reset, and replay.
Exercise error and cancellation states separately; a successful static page load
does not validate the editing flow.

On October 22, 2026, browser interaction at a narrow viewport verified all four
prepared actions in no-model mode, passing structural checks, baseline carry-over
when changing actions, and recorded replay. The previews stacked vertically.
Desktop widths, keyboard/contrast checks, browser downloads, cancellation/failure
states, and Microsoft PowerPoint review remain pending. The HTTP suite verifies
the native download response separately.

## Real custom-instruction evidence

On October 22, 2026, a browser-triggered real run requesting `gpt-6.1-sol` / `medium`
requested a yellow square in the bottom-right corner labeled Hello, preserving
existing content. The CLI completed with exit code 0. Total action time was
5.9325 seconds; Codex request elapsed was 5.8582 seconds. No CLI warning was recorded.
Inspection of the saved native PPTX found one new 160 × 160 yellow (`#FFFF00`)
square with text Hello; all original shapes and the background were unchanged.
The browser displayed the model reply and **Review needed**, with structural
checks passing. This verifies one custom edit, not general prompt reliability
or an isolated model-performance comparison. PowerPoint visual review remains pending.
Browser checks also confirmed blank-input disabling, switching model without
changing the baseline, promoting the last result after changing the instruction,
resetting, exact-instruction history filtering, and replay without a new request.

## Further real model acceptance — pending

Use the background action from the original baseline with each exact prepared
configuration. Record success or failure, requested model/effort, observed
elapsed time and usage, saved output, checks, and any CLI warning.
Inspect downloaded files in Microsoft PowerPoint. Then exercise the other three
actions, cancellation, failure, replay, and process restart.
Do not treat an authentication check or simple text reply as a completed slide edit.

## Interpretation

Total action time and request elapsed are wall-clock observations, not pure
inference time. Exposed token counters do not provide dollar cost, energy, or
hardware utilization. Structural audits do not replace visual or user review.
The current configurations use different reasoning efforts, so they do not
isolate a model-only effect.

Broader comparisons need repeated trials, alternating order, no-change cases,
and checks for damage outside the requested edit. Difficulty labels need explicit
criteria before they can support a selection policy. No ranking follows from
the current offline tests.
