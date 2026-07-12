PR Factory
AI as Agency track, Hermes Buildathon

Drop a GitHub issue link and an agent org ships the fix: a planner decomposes it, parallel coder agents race in isolated worktrees, a judge picks the winning diff, QA runs the tests, and a real pull request lands with the full decision trail attached.


How to build it, step by step
1. Put a waitlist page live before you build anything: one headline, one email field, hosted on Cloudflare Pages.
2. Prove the loop on one tiny issue: planner to a single coder to a posted PR, end to end.
3. Add the race: two coder subagents in isolated worktrees with a judge picking by spec and tests.
4. Wire the QA stage so no PR posts without the suite passing.
5. Build the live kanban and log every run, verdict, and cost in Convex.
6. Add memory so conventions from merged and rejected PRs carry into the next run.
7. Run the factory on five real issues across two repos and merge what deserves it.
8. Rehearse the demo: live issue in, real PR out, ending on the merged count.


What you will need
- Planner agent decomposing an issue into a spec with acceptance checks
- Two or more coder subagents racing in isolated git worktrees
- Judge agent picking the winning diff against the spec and tests
- QA stage running the real test suite before the PR posts
- Hermes memory carrying codebase conventions across runs
- Live kanban showing every agent, stage, and handoff
- Convex logging runs, verdicts, costs, and latency

Memory and self-learning
- Remembers you: memory holds repo conventions and past review feedback, so run five writes in your style; L4 is the planner citing a convention learned from a rejected earlier PR.
- Learns from use: merged versus rejected PRs reweight which coder strategies win; L4 wires merge outcomes into judge criteria automatically, with win rates before and after.

Your demo moment
Paste a live issue, watch the kanban as coders race and the judge rules, then open the real PR it just posted with tests green and the decision trail, and end on the count of PRs merged today, real output on a real surface, the 20x root.

Deploy: Hermes subagents and memory at the core, GitHub as the live surface, live kanban dashboard on Cloudflare Pages, Convex storing runs, verdicts, and costs.
Proof bar: Real PRs opened and merged during the event with linked decision trails, plus per-run cost and test results.
Scoring note: Merged PRs on real repos are the 20x root at its strongest; the race-plus-judge org is legible structure (5x), the kanban is observability (7x), and picking winners by tests is evaluation.