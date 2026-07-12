from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pr_factory.agents.prompts import compact_json
from pr_factory.agents.schemas import CoderInput, CoderResult
from pr_factory.observability import get_logger

logger = get_logger(__name__)


def should_apply_changes() -> bool:
    return os.getenv("PR_FACTORY_CODER_APPLY", "true").strip().lower() not in {"0", "false", "no", "off"}


def apply_coder_result(coder_input: CoderInput, coder_result: CoderResult) -> CoderResult:
    if not should_apply_changes():
        return coder_result

    repo_path = Path(coder_input.repo_path).resolve()
    timeout = int(os.getenv("PR_FACTORY_CODER_TIMEOUT", "900"))
    prompt = build_code_worker_prompt(coder_input, coder_result)
    logger.info("Running code worker for task_id=%s in %s", coder_input.task_id, repo_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", prefix="pr-factory-coder-", delete=False) as prompt_file:
        prompt_file.write(prompt)
        prompt_path = Path(prompt_file.name)
    try:
        completed = subprocess.run(
            _worker_command(prompt_path),
            cwd=str(repo_path),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    finally:
        prompt_path.unlink(missing_ok=True)

    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode != 0:
        raise RuntimeError(f"Code worker failed with exit code {completed.returncode}: {output}")
    updated = coder_result.model_copy(
        update={
            "applied": True,
            "worker_output": output[-8000:] if output else "Code worker completed with no output.",
        }
    )
    logger.info("Code worker completed for task_id=%s", coder_input.task_id)
    return updated


def _worker_command(prompt_path: Path) -> list[str]:
    command = os.getenv("PR_FACTORY_CODER_COMMAND", "python-agent").strip().lower()
    model = os.getenv("PR_FACTORY_AGENT_MODEL", "gpt-5.5")
    if command in {"python-agent", "agent", "aia", "hermes"}:
        script = (
            "import sys; "
            "from pathlib import Path; "
            "from run_agent import AIAgent; "
            "prompt=Path(sys.argv[1]).read_text(encoding='utf-8'); "
            f"agent=AIAgent(model={model!r}, quiet_mode=True); "
            "print(agent.chat(prompt))"
        )
        return [sys.executable, "-c", script, str(prompt_path)]
    return [command, str(prompt_path)]


def build_code_worker_prompt(coder_input: CoderInput, coder_result: CoderResult) -> str:
    return f"""
You are the PR Factory code-editing worker running inside the cloned repository.

Task:
- Apply the requested fix for exactly this task.
- Modify files directly in this working tree.
- Do not commit, push, or create a pull request.
- Inspect files before editing.
- Make the smallest safe change.
- Run the focused tests listed below when feasible.
- If a command cannot run because dependencies are missing, report the blocker clearly.

Task metadata:
{compact_json(coder_input.model_dump())}

Coder plan to execute:
{compact_json(coder_result.model_dump())}

After editing, respond with:
- files changed
- tests/commands run
- results
- blockers, if any
""".strip()
