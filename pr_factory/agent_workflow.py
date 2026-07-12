from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from pr_factory.agents import CoderAgent, CoderInput, PlannerAgent, PlannerInput
from pr_factory.github_tool import GitHubIssue
from pr_factory.observability import get_logger
from pr_factory.repo_investigation import RepositoryInvestigation
from pr_factory.task_store import TaskStore

logger = get_logger(__name__)


def run_planner_coder_workflow(
    *,
    issue: GitHubIssue,
    issue_url: str,
    repo_path: str,
    signal_analysis: dict[str, Any],
    investigation: RepositoryInvestigation,
    vector_context: list[dict[str, Any]] | None = None,
    planner_agent: PlannerAgent | None = None,
    coder_agent: CoderAgent | None = None,
) -> TaskStore:
    """Run resumable planner -> coder workflow backed by a local task store."""

    store = TaskStore.for_issue(repo_path, issue)
    vector_context = vector_context or []
    logger.info("Loaded task store path=%s", store.path)
    planner_agent = planner_agent or PlannerAgent()
    coder_agent = coder_agent or CoderAgent()

    if not store.has_planner_brief():
        planner_input = build_planner_input(
            issue=issue,
            issue_url=issue_url,
            repo_path=repo_path,
            signal_analysis=signal_analysis,
            investigation=investigation,
            vector_context=vector_context,
        )
        planner_brief = planner_agent.plan(planner_input)
        store.set_planner_brief(planner_brief)
        logger.info("Planner brief stored with %s tasks", len(store.tasks))

    while True:
        task = store.claim_next_task()
        if task is None:
            break
        try:
            coder_input = CoderInput(
                repo_path=repo_path,
                planner_brief=store.planner_brief,
                project_stack=_to_plain(investigation.stack),
                candidate_files=[_to_plain(candidate) for candidate in investigation.candidate_files],
                vector_context=vector_context,
                relevant_tests=investigation.relevant_tests,
                task_id=task.id,
                task_title=task.title,
                task_focus=task.relevant_file,
            )
            coder_result = coder_agent.execute(coder_input)
            store.complete_task(task.id, coder_result)
            logger.info("Coder task completed id=%s", task.id)
        except Exception as error:  # noqa: BLE001 - persisted for resumability.
            store.fail_task(task.id, str(error))
            logger.exception("Coder task failed id=%s", task.id)
            break

    return store


def build_planner_input(
    *,
    issue: GitHubIssue,
    issue_url: str,
    repo_path: str,
    signal_analysis: dict[str, Any],
    investigation: RepositoryInvestigation,
    vector_context: list[dict[str, Any]] | None = None,
) -> PlannerInput:
    return PlannerInput(
        issue_url=issue_url,
        issue_title=issue.title,
        issue_body=issue.body,
        issue_comments=[comment.get("body", "") for comment in issue.comments if comment.get("body")],
        signal_analysis=signal_analysis,
        project_stack=_to_plain(investigation.stack),
        candidate_files=[_to_plain(candidate) for candidate in investigation.candidate_files],
        vector_context=vector_context or [],
        relevant_tests=investigation.relevant_tests,
        repo_path=repo_path,
    )


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value
