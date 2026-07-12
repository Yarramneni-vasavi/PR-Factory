# Requirements

## Execution
- Planner agent should decompose an issue into an acceptance criteria
- Two or more coder subagents racing in isolated git worktrees to solve this issue
- each individual agent should run the unit tests in the repo and give the pass percentage
- Judge agent picking the winning diff against the spec and tests

## Verification
- QA stage running the real test suite before the PR posts
- Hermes memory carrying codebase conventions across runs

## Observability
- Live kanban showing every agent, stage, and handoff
- Convex logging runs, verdicts, costs, and latency

## Memory and self-learning
- Remembers you: memory holds repo conventions and past review feedback, so run five writes in your style; L4 is the planner citing a convention learned from a rejected earlier PR.
- Learns from use: merged versus rejected PRs reweight which coder strategies win; L4 wires merge outcomes into judge criteria automatically, with win rates before and after.