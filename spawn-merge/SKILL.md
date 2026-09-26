---
name: spawn-merge
description: Decide and merge GitHub PRs in parallel.
---

Read the /merge, /takeover, and /close skills before starting.
The skill argument can be used to filter the PRs in scope.

The goal is to evaluate the open PRs in the repository and decide which ones to merge.
Each merge is performed in parallel by a sub-agent.

Recommend an action for every PR: /merge (addressing any minor issues), skip, or /close.
Start /merge right away for PRs you'd merge with no open question.
Interactively prompt the user about the rest, a few PRs per prompt, with your recommendation first and room for questions.

Run each /merge or /close in its own sub-agent.
Merges mostly wait on GitHub, so there is no fixed cap; other sessions share this machine, so hold new agents while the load average exceeds the core count.
Each sub-agent blocks on its own waits and reports back only when done or blocked.

Keep going until all PRs have been decided then wait for all spawned sub-agents to finish.
Before finishing, refresh the open PR list and process any new PRs in scope.

Summarize the results when done.
Include all of the issues encountered and suggested follow-ups.
