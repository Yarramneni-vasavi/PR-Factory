from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from pr_factory.observability import get_logger
from pr_factory.repo_investigation import ProjectStack
from pr_factory.task_store import TaskStore

logger = get_logger(__name__)


@dataclass(frozen=True)
class CommandRun:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class QAResult:
    passed: bool
    test_runs: list[CommandRun] = field(default_factory=list)
    coverage_run: CommandRun | None = None

    @property
    def coverage_report(self) -> str:
        if not self.coverage_run:
            return "Coverage was not run."
        output = "\n".join(part for part in (self.coverage_run.stdout, self.coverage_run.stderr) if part).strip()
        return output or "Coverage command produced no output."


def run_qa(repo_path: str | Path, task_store: TaskStore, stack: ProjectStack) -> QAResult:
    commands = _test_commands(task_store, stack)
    test_runs = [_run(command, repo_path) for command in commands]
    tests_passed = bool(test_runs) and all(run.ok for run in test_runs)
    coverage = _run_coverage(repo_path, stack, commands[0] if commands else None)
    logger.info("QA finished passed=%s tests=%s coverage=%s", tests_passed, len(test_runs), bool(coverage))
    return QAResult(passed=tests_passed, test_runs=test_runs, coverage_run=coverage)


def _test_commands(task_store: TaskStore, stack: ProjectStack) -> list[str]:
    commands: list[str] = []
    if task_store.planner_brief:
        commands.extend(task_store.planner_brief.tests_to_run)
    commands.extend(stack.test_commands)
    seen = set()
    result = []
    for command in commands:
        command = command.strip()
        if command and command not in seen:
            seen.add(command)
            result.append(command)
    return result or ["python -m pytest -q"]


def _run_coverage(repo_path: str | Path, stack: ProjectStack, first_test_command: str | None) -> CommandRun | None:
    explicit = os.getenv("PR_FACTORY_COVERAGE_COMMAND", "").strip()
    if explicit:
        return _run(explicit, repo_path)
    if "Python" not in stack.languages:
        return None
    source = "src" if "src" in stack.source_dirs else "."
    test_target = ""
    if first_test_command and "pytest" in first_test_command:
        parts = first_test_command.split()
        test_target = " ".join(part for part in parts if part.startswith("tests"))
    command = f"python -m pytest {test_target} --cov={source} --cov-report=term-missing -q".strip()
    return _run(command, repo_path)


def _run(command: str, repo_path: str | Path) -> CommandRun:
    command = _command_for_repo(command, repo_path)
    logger.info("Running QA command: %s", command)
    completed = subprocess.run(
        command,
        cwd=str(Path(repo_path)),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True,
        check=False,
        timeout=int(os.getenv("PR_FACTORY_TEST_TIMEOUT", "900")),
    )
    return CommandRun(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout[-12000:],
        stderr=completed.stderr[-12000:],
    )


def _command_for_repo(command: str, repo_path: str | Path) -> str:
    repo = Path(repo_path)
    if "pytest" in command and (repo / "pyproject.toml").exists() and shutil.which("uv"):
        if not command.strip().startswith("uv "):
            return f"uv run {command}"
    return command
