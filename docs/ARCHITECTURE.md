# Initial Architecture

## Phase 1: Single coder with deterministic codebase investigation

Drop a GitHub issue link --> [MY PR Agent] --> ships the fix [Create A PR]

### Architecture decision

Phase 1 will not require a vector database.

The cloned repository is the source of truth. Relevant code will be identified through deterministic investigation:
- issue text extraction
- exact search over the local repository
- symbol, import, and usage tracing
- test failure output
- neighboring file inspection

A vector index may be added in a later phase as an optional retrieval layer for large repositories or vague issues, but it must not replace deterministic code search and test-driven investigation.

### Investigation pipeline

1. Fetch GitHub issue
    - Read the issue title, description, labels, comments, and linked references if available.
    - Extract useful signals:
        - error messages
        - stack traces
        - file paths
        - function, class, component, or module names
        - route names, endpoint names, CLI commands, and test names
        - reproduction steps
        - expected behavior versus actual behavior

2. Clone repository locally
    - Clone the repository referenced by the GitHub issue.
    - Keep the local clone as the source of truth for all code investigation.

3. Detect project stack
    - Identify language and framework.
    - Identify package manager and dependency files, such as `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, or `go.mod`.
    - Identify test framework and likely test commands.
    - Identify source directories, test directories, and important configuration files.

4. Search the repository
    - Search exact error messages and stack trace fragments first.
    - Search symbols, filenames, routes, endpoint names, test names, and domain terms from the issue.
    - Rank candidate files by issue relevance, path relevance, source/test proximity, and whether they appear in stack traces or search hits.

5. Inspect candidate files
    - Read the top candidate files.
    - Trace definitions and usages for relevant symbols.
    - Trace imports and callers to understand the affected call chain.
    - Inspect neighboring files to learn local implementation patterns.
    - Find related tests or nearby test coverage.

6. Run relevant tests when possible
    - Run the most focused test command first if a relevant test is identified.
    - If no focused test exists, run the smallest useful test subset.
    - Use test failure output as another source of evidence for relevant files and root cause.

7. Planner agent produces the fix brief
    - Summarize the issue.
    - Define acceptance criteria.
    - List relevant files and why each file is relevant.
    - State the suspected root cause.
    - Propose a fix strategy.
    - Specify tests the coder should run.

8. Coder agent implements the fix
    - Inspect the planner's relevant files before editing.
    - Make the smallest code change that satisfies the acceptance criteria.
    - Add or update tests when appropriate.
    - Run the focused tests and report results.

9. QA verifies the result
    - Run the broader test suite or the best available verification command.
    - Block PR creation if verification fails.

10. GitHub PR creation
    - Create a pull request only after QA passes.
    - Attach the issue summary, acceptance criteria, files changed, tests run, and decision trail to the PR description.