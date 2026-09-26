---
name: decisions
description: Hand a finished task's result to the user with its open decisions, readiness, and follow-ups. Read by other skills when a task or sub-agent reports back.
---

When a task finishes, yours or a sub-agent's, hand the result to the user before moving on.

1. Explain the result in a few lines: what changed, what was verified, and what was not.
2. Prompt interactively for every open decision: opinions (naming, API shape, target branch) and blockers (releases, approvals, manual steps). Batch a few per prompt, each with the PR, a short summary, and your recommendation first.
3. Offer the follow-ups as a multi-select to plan or skip.
4. When nothing is open, ask whether to mark the PR ready or proceed.

Keep a PR a draft while any decision is open.
Relay each answer to whoever owns the work, and prompt again on anything its next report raises.
A background sub-agent cannot prompt the user: it lists its decisions with recommendations in its report and leaves the prompting, and the ready switch, to its coordinator.
