# Planner Code Investigation Skill

Use this skill when turning a GitHub issue and deterministic repository investigation into a coder-ready fix brief.

## Planning rules

1. Treat the cloned repository and investigation output as source of truth.
2. Prefer exact evidence over guesses: stack traces, file paths, symbols, route names, test names, and deterministic search hits.
3. Do not invent files, functions, APIs, dependencies, or test commands.
4. Select the smallest set of files the coder must inspect first.
5. Explain why every relevant file is included.
6. Convert issue behavior into concrete acceptance criteria.
7. Include focused tests before broad tests.
8. If relevant tests are missing, tell the coder what test should be added or updated.
9. Flag risks when the suspected fix may mask a deeper issue.

## Fix brief shape

The planner brief should make the coder's next step obvious:

- Issue summary: one concise statement of the bug.
- Acceptance criteria: observable checks that prove the issue is fixed.
- Relevant files: files to inspect/change, with reasons and priorities.
- Suspected root cause: evidence-backed hypothesis, or null if unknown.
- Fix strategy: smallest safe implementation approach.
- Tests to run: focused commands first, broad verification after.
- Decision notes: evidence trail from issue signals and repository search.

## Prioritization

Use high priority for files with direct evidence:

- Appears in stack trace.
- Matches exact symbol from issue.
- Contains exact error message or failing route/test name.
- Is imported by or imports another high-evidence file.

Use medium priority for nearby tests and adjacent implementation patterns.
Use low priority for broad contextual files that may only be needed if the direct path fails.
