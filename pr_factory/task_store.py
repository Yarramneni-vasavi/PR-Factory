from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pr_factory.agents.schemas import CoderResult, PlannerBrief, RelevantFile
from pr_factory.github_tool import GitHubIssue

TaskStatus = Literal["pending", "running", "completed", "failed"]
STORE_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentTask:
    id: str
    title: str
    status: TaskStatus = "pending"
    relevant_file: dict[str, Any] | None = None
    coder_result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentTask":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            status=data.get("status", "pending"),
            relevant_file=data.get("relevant_file"),
            coder_result=data.get("coder_result"),
            error=data.get("error"),
            attempts=int(data.get("attempts", 0)),
            created_at=data.get("created_at") or utc_now(),
            updated_at=data.get("updated_at") or utc_now(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskStore:
    """Durable local planner/coder task store.

    Stored under the cloned repository so long-running agent work can resume
    after a crash without re-running completed planner/coder steps.
    """

    def __init__(self, path: str | Path, issue_url: str, issue_number: int) -> None:
        self.path = Path(path)
        self.issue_url = issue_url
        self.issue_number = issue_number
        self.planner_brief: PlannerBrief | None = None
        self.tasks: list[AgentTask] = []
        self.version = STORE_VERSION
        self.created_at = utc_now()
        self.updated_at = utc_now()

    @classmethod
    def for_issue(cls, repo_path: str | Path, issue: GitHubIssue) -> "TaskStore":
        path = Path(repo_path) / ".pr-factory" / "tasks" / f"issue-{issue.number}.json"
        if path.exists():
            store = cls.load(path)
            store.upgrade_if_needed()
            store.recover_running_tasks()
            store.recover_retryable_failed_tasks()
            return store
        store = cls(path, issue.html_url, issue.number)
        store.save()
        return store

    @classmethod
    def load(cls, path: str | Path) -> "TaskStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls(path, data["issue_url"], int(data["issue_number"]))
        store.created_at = data.get("created_at") or utc_now()
        store.updated_at = data.get("updated_at") or utc_now()
        store.version = int(data.get("version", 1))
        if data.get("planner_brief"):
            store.planner_brief = PlannerBrief.model_validate(data["planner_brief"])
        store.tasks = [AgentTask.from_dict(task) for task in data.get("tasks", [])]
        return store

    def save(self) -> None:
        self.updated_at = utc_now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "issue_url": self.issue_url,
            "version": self.version,
            "issue_number": self.issue_number,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "planner_brief": self.planner_brief.model_dump() if self.planner_brief else None,
            "tasks": [task.to_dict() for task in self.tasks],
        }
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def upgrade_if_needed(self) -> None:
        if self.version >= STORE_VERSION:
            return
        if self.planner_brief:
            self.tasks = planner_brief_to_tasks(self.planner_brief)
        else:
            self.tasks = []
        self.version = STORE_VERSION
        self.save()

    def recover_running_tasks(self) -> None:
        changed = False
        for task in self.tasks:
            if task.status == "running":
                task.status = "pending"
                task.error = "Recovered from interrupted running state."
                task.updated_at = utc_now()
                changed = True
        if changed:
            self.save()

    def recover_retryable_failed_tasks(self) -> None:
        changed = False
        for task in self.tasks:
            if task.status == "failed" and task.error and _is_retryable_task_error(task.error):
                task.status = "pending"
                task.error = f"Recovered retryable failure: {task.error}"
                task.updated_at = utc_now()
                changed = True
        if changed:
            self.save()

    def has_planner_brief(self) -> bool:
        return self.planner_brief is not None

    def set_planner_brief(self, planner_brief: PlannerBrief) -> None:
        self.planner_brief = planner_brief
        if not self.tasks:
            self.tasks = planner_brief_to_tasks(planner_brief)
        self.save()

    def claim_next_task(self) -> AgentTask | None:
        for task in self.tasks:
            if task.status == "pending":
                task.status = "running"
                task.attempts += 1
                task.error = None
                task.updated_at = utc_now()
                self.save()
                return task
        return None

    def complete_task(self, task_id: str, coder_result: CoderResult) -> None:
        task = self._task(task_id)
        task.status = "completed"
        task.coder_result = coder_result.model_dump()
        task.error = None
        task.updated_at = utc_now()
        self.save()

    def fail_task(self, task_id: str, error: str) -> None:
        task = self._task(task_id)
        task.status = "failed"
        task.error = error
        task.updated_at = utc_now()
        self.save()

    def all_done(self) -> bool:
        return bool(self.tasks) and all(task.status == "completed" for task in self.tasks)

    def summary_counts(self) -> dict[str, int]:
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for task in self.tasks:
            counts[task.status] += 1
        return counts

    def _task(self, task_id: str) -> AgentTask:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Unknown task id: {task_id}")


def planner_brief_to_tasks(planner_brief: PlannerBrief) -> list[AgentTask]:
    files = planner_brief.relevant_files or []
    if not files:
        return [
            AgentTask(
                id="task-001",
                title="Implement planner fix strategy",
                relevant_file=None,
            )
        ]

    return [
        AgentTask(
            id=f"task-{index:03d}",
            title=f"Handle {file.path}",
            relevant_file=_relevant_file_dict(file),
        )
        for index, file in enumerate(files, start=1)
    ]


def _relevant_file_dict(file: RelevantFile) -> dict[str, Any]:
    return file.model_dump()


def _is_retryable_task_error(error: str) -> bool:
    retryable_markers = (
        "[WinError 206]",
        "filename or extension is too long",
        "Code worker failed with exit code",
    )
    return any(marker in error for marker in retryable_markers)
