# PR Factory

PR Factory is an agentic GitHub issue-to-PR pipeline built for the Hermes Buildathon "AI as Agency" track.

Give it a GitHub issue URL. It fetches the issue, decides whether it is a real bug, clones the target repo, investigates the codebase with deterministic search plus Qdrant vector context, asks planner/coder agents to implement the fix, runs local QA/coverage, and opens a GitHub pull request when verification passes.

## Current capabilities

- Fetch GitHub issue details, labels, comments, and state.
- Stop early for closed/non-open issues.
- Triage issues into bug vs feature/enhancement/not-bug.
- Clone or reuse repositories under `./.projects/{owner}/{repo}`.
- Detect project stack, package manager, source dirs, test dirs, and likely test commands.
- Run deterministic repository investigation from issue signals.
- Index/retrieve code chunks with Qdrant and pass vector context to agents.
- Use planner/coder agents with default model `gpt-5.5`.
- Persist long-running work in a local task store for crash recovery.
- Apply code changes through a coder worker inside the cloned repo.
- Run tests and best-effort coverage.
- Commit, push, and create a GitHub PR only after QA passes.
- Log project activity to `pr_factory.log` by default.

## High-level flow

```text
GitHub issue URL
  -> fetch issue
  -> skip if issue is not open
  -> triage bug signals
  -> skip if not a bug
  -> clone/reuse repo under .projects/
  -> create/check out issue branch
  -> detect project stack
  -> deterministic code search
  -> Qdrant vector indexing + retrieval
  -> planner agent creates fix brief
  -> task store creates durable coder tasks
  -> coder agent applies changes task-by-task
  -> QA runs tests + coverage
  -> publish PR with analysis, fix details, and coverage report
```

## Repository layout

```text
.
├── main.py                         # Thin CLI entrypoint
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── docs/                           # Vision, architecture, requirements
├── pr_factory/
│   ├── cli/                        # CLI args, output formatting, main flow
│   ├── agents/                     # Planner/coder schemas, prompts, workers, LLM backend
│   ├── context/                    # Code parsing, Qdrant indexing/retrieval
│   ├── observability/              # File logger
│   ├── github_tool.py              # GitHub REST and git helpers
│   ├── repo_investigation.py       # Deterministic repository investigation
│   ├── task_store.py               # Durable planner/coder task store
│   ├── qa.py                       # Test and coverage runner
│   ├── publisher.py                # Commit, push, PR creation
│   └── repository.py               # Clone path and branch helpers
└── tests/                          # Unit tests
```

## Prerequisites

- Python 3.11+
- Git
- Hermes Agent CLI available on PATH or importable `run_agent` package
- Optional: `uv` for running target Python project tests
- Optional: Qdrant server. If `QDRANT_URL` is not set or fails, PR Factory falls back to embedded local Qdrant.
- GitHub token with repo write permissions if you want PR creation.

## Setup

1. Create and activate a virtual environment.

   Windows PowerShell:

   ```powershell
   python -m venv .hermes_env
   .\.hermes_env\Scripts\Activate.ps1
   ```

   Bash/Git Bash:

   ```bash
   python -m venv .hermes_env
   source .hermes_env/Scripts/activate
   ```

2. Install dependencies.

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Create your local env file.

   ```bash
   cp .env.example .env
   ```

4. Edit `.env` and set at least:

   ```env
   GITHUB_TOKEN=your_token_here
   PR_FACTORY_AGENT_MODEL=gpt-5.5
   PR_FACTORY_SIGNAL_AGENT_MODEL=gpt-5-mini
   ```

Do not commit `.env`.

## Environment variables

Important variables from `.env.example`:

### GitHub

```env
GITHUB_TOKEN=
GITHUB_API_URL=https://api.github.com
```

`GITHUB_TOKEN` is required for private repos, pushing branches, and creating PRs.

### Agent models

```env
PR_FACTORY_AGENT_MODEL=gpt-5.5
PR_FACTORY_SIGNAL_AGENT_MODEL=gpt-5-mini
PR_FACTORY_LLM_BACKEND=hermes
PR_FACTORY_LLM_BASE_URL=
PR_FACTORY_LLM_API_KEY=
OPENAI_API_KEY=
```

Planner and coder use `PR_FACTORY_AGENT_MODEL`. Issue triage uses `PR_FACTORY_SIGNAL_AGENT_MODEL`.

### Embeddings and Qdrant

```env
PR_FACTORY_EMBEDDINGS_PROVIDER=hash
PR_FACTORY_EMBEDDINGS_MODEL=hash-384
PR_FACTORY_EMBEDDINGS_DIM=384
PR_FACTORY_QDRANT_COLLECTION=pr_factory_code_chunks
QDRANT_URL=
QDRANT_API_KEY=
PR_FACTORY_QDRANT_PATH=.qdrant
PR_FACTORY_QDRANT_RECREATE=false
PR_FACTORY_USE_QDRANT=true
PR_FACTORY_QDRANT_TOP_K=8
```

Default embeddings are deterministic local hash embeddings, so Qdrant retrieval works without an external embedding API. Set `PR_FACTORY_EMBEDDINGS_PROVIDER=openai` to use an OpenAI-compatible embeddings endpoint.

If `QDRANT_URL` is empty, embedded local Qdrant is used via `PR_FACTORY_QDRANT_PATH`. If remote Qdrant fails, the system falls back to local embedded Qdrant.

### Coder execution

```env
PR_FACTORY_CODER_APPLY=true
PR_FACTORY_CODER_COMMAND=python-agent
PR_FACTORY_CODER_TIMEOUT=900
```

`python-agent` invokes Hermes' `AIAgent` through Python and avoids Windows command-line length limits by passing the worker prompt through a temporary file.

### Tests and coverage

```env
PR_FACTORY_TEST_TIMEOUT=900
PR_FACTORY_COVERAGE_COMMAND=
```

If `PR_FACTORY_COVERAGE_COMMAND` is empty, Python projects use a best-effort pytest coverage command.

### Logging

```env
PR_FACTORY_LOG_FILE=pr_factory.log
PR_FACTORY_LOG_LEVEL=INFO
```

Logs are written to the repo root by default.

## Running PR Factory

Basic run:

```bash
python ./main.py issue_url=https://github.com/owner/repo/issues/123
```

Equivalent forms:

```bash
python ./main.py https://github.com/owner/repo/issues/123
python ./main.py --issue-url https://github.com/owner/repo/issues/123
```

Skip comments:

```bash
python ./main.py --no-comments https://github.com/owner/repo/issues/123
```

Use a GitHub Enterprise API URL:

```bash
python ./main.py --api-url https://github.example.com/api/v3 https://github.example.com/owner/repo/issues/123
```

## What happens during a run

1. The issue is fetched from GitHub.
2. Non-open issues are skipped.
3. Triage extracts file paths, symbols, errors, reproduction steps, and expected/actual behavior.
4. Non-bug issues are skipped.
5. The repo is cloned or reused under `.projects/`.
6. A branch like `pr-factory/issue-123-short-title` is checked out.
7. The project stack is detected and cached in the cloned repo.
8. Deterministic search ranks candidate files and relevant tests.
9. Qdrant indexes source chunks and returns semantic/lexical context.
10. Planner creates a fix brief.
11. The task store writes `.pr-factory/tasks/issue-{number}.json` inside the cloned repo.
12. Coder tasks run one by one and update task status.
13. QA runs focused/broad tests and coverage.
14. If all tests pass and source/test files changed, PR Factory commits, pushes, and opens a GitHub PR.

## Local files created at runtime

Inside this repo:

```text
.projects/        # cloned target repositories
.qdrant/          # local Qdrant storage if configured
pr_factory.log    # runtime logs
```

Inside each cloned target repo:

```text
.pr-factory/project_stack.json       # detected stack cache
.pr-factory/tasks/issue-{number}.json # durable task store
```

The publisher excludes `.pr-factory/` files from commits.

## Task store and resumability

The task store supports long-running work:

- `pending`: task not started
- `running`: task currently executing
- `completed`: coder finished and applied work
- `failed`: task failed with error details

On restart:

- interrupted `running` tasks are returned to `pending`
- known retryable worker failures are requeued
- completed tasks are not rerun

## Qdrant behavior

PR Factory uses both retrieval paths:

- deterministic search for exact issue signals, file paths, symbols, and tests
- Qdrant vector context for semantic/lexical code chunks

The CLI prints a `Qdrant Vector Context` section so you can inspect what was retrieved.

If it shows `none retrieved`, check `pr_factory.log`. Common causes:

- bad `QDRANT_URL`
- Qdrant server unavailable
- no parsable source files
- collection/vector dimension mismatch

Remote Qdrant failures should fall back to embedded local Qdrant.

## QA and PR creation

QA runs only when all coder tasks are completed.

PR creation is blocked when:

- coder tasks are incomplete
- tests fail
- no source/test files changed
- git push fails
- GitHub API PR creation fails

The PR body includes:

- issue summary
- acceptance criteria
- changed files
- tests run
- deterministic investigation summary
- task execution summary
- coverage report

## Useful development commands

Run the test suite:

```bash
python -m unittest discover -v
```

Compile key files:

```bash
python -m py_compile main.py pr_factory/cli/main.py pr_factory/agents/coder.py pr_factory/agents/planner.py
```

Inspect git state of a cloned target repo:

```bash
git -C .projects/OWNER/REPO status --short
```

View logs:

```bash
tail -n 120 pr_factory.log
```

## Troubleshooting

### `No module named pytest`

The target repo may not have its test dependencies installed. If it has `pyproject.toml` and `uv` is installed, PR Factory prefixes pytest commands with `uv run`. Otherwise install the target repo dependencies manually inside the cloned repo.

### Qdrant warning or `404 page not found`

Your `QDRANT_URL` may not point to a valid Qdrant API endpoint. Leave `QDRANT_URL` empty to use embedded local Qdrant.

### Windows `[WinError 206] filename or extension is too long`

Use:

```env
PR_FACTORY_CODER_COMMAND=python-agent
```

This is the default and passes prompts via temporary files.

### PR is skipped

Check the printed `GitHub Pull Request` section. PR creation is skipped when QA failed, no changed files exist, or coder tasks are incomplete.

## Current limitations

- Phase 1 uses one coder workflow, not a full racing multi-coder/judge setup yet.
- Qdrant is an augmentation, not the source of truth.
- Test/coverage commands are best-effort and depend on the cloned repo's dependency setup.
- GitHub push/PR requires working credentials and write access.

## Safety notes

- Do not commit `.env` or credentials.
- `GITHUB_TOKEN` must never be logged or printed.
- PR Factory stores local task metadata under `.pr-factory/` in cloned repos, but excludes that directory from commits.
