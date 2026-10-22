# From one experiment to task-specific selection

The research question is: which model and reasoning effort achieve an acceptable
result for this task, within a useful waiting-time and resource budget?
The first decision is what counts as acceptable; the fastest wrong output is not
a useful optimum.

| Stage | Concrete outcome | Evidence required |
| --- | --- | --- |
| 1. Slide experiment | A usable local app with fixed input, bounded tools, downloads, and measured runs | Offline tests, browser QA, real structured calls, and native PPTX review |
| 2. Task evaluation | Explicit task families, difficulty criteria, and success/preservation rubrics | Repeated trials, failure/no-change cases, human review, and held-out tasks |
| 3. Tradeoff analysis | Compare configurations against quality thresholds and waiting-time budgets | Comparable inputs, reported variance, exact settings, and measured usage limits |
| 4. Selection policy | Recommend a configuration for a stated task and budget | Evaluation against fixed baselines on held-out tasks; report failures and uncertainty |

Only the first stage has a starter implementation. The later stages are a plan,
not working features or demonstrated savings.

## App direction

Keep the interaction small: choose a task, select configurations, run, compare
outputs, and inspect why a result passed or failed. Broader task adapters should
reuse the comparison and run-recording model without forcing every task into a
slide preview. Keep quality, elapsed time, and available usage visible separately.

Task difficulty is not inferred from prompt length. Token usage is not equated
with total compute or energy. A future recommendation must state its quality
threshold, budget, evidence, and uncertainty rather than hiding them in a single
score. Automatic routing, cloud deployment, and broad benchmarks are separate
implementation decisions after the first experiment is validated.
