from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pr_factory.github_tool import GitHubClient, GitHubIssue, GitRepository, PullRequest, build_pr_body
from pr_factory.observability import get_logger
from pr_factory.qa import QAResult
from pr_factory.repo_investigation import RepositoryInvestigation
from pr_factory.task_store import TaskStore

logger = get_logger(__name__)


@dataclass(frozen=True)
class PublishResult:
    changed_files: list[str]
    branch: str | None
    commit_created: bool
    pushed: bool
    pull_request: PullRequest | None
    skipped_reason: str | None = None


def publish_fix(
    *,
    repo: GitRepository,
    issue: GitHubIssue,
    task_store: TaskStore,
    investigation: RepositoryInvestigation,
    qa_result: QAResult,
    branch: str,
    github_client: GitHubClient | None = None,
) -> PublishResult:
    changed_files = changed_working_files(repo)
    if not changed_files:
        return PublishResult(changed_files=[], branch=branch, commit_created=False, pushed=False, pull_request=None, skipped_reason="No source/test changes to publish.")
    if not qa_result.passed:
        return PublishResult(changed_files=changed_files, branch=branch, commit_created=False, pushed=False, pull_request=None, skipped_reason="QA failed; PR creation blocked.")

    repo.add(changed_files)
    message = f"Fix issue #{issue.number}: {issue.title}"
    commit_result = repo.commit(message, allow_empty=False)
    if not commit_result.ok:
        raise RuntimeError(commit_result.stderr or commit_result.stdout)

    _set_authenticated_origin(repo, issue)
    repo.push(branch=branch)
    body = build_pull_request_body(issue, task_store, investigation, qa_result, changed_files)
    client = github_client or GitHubClient()
    pr = client.create_pull_request(
        repository=issue.repository,
        title=message,
        body=body,
        head=branch,
        base=repo.default_branch(),
    )
    logger.info("Created pull request %s", pr.html_url)
    return PublishResult(changed_files=changed_files, branch=branch, commit_created=True, pushed=True, pull_request=pr)


def changed_working_files(repo: GitRepository) -> list[str]:
    result = repo.git(["status", "--porcelain"], check=False)
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.replace("\\", "/")
        if path.startswith(".pr-factory/"):
            continue
        files.append(path)
    return sorted(set(files))


def build_pull_request_body(issue: GitHubIssue, task_store: TaskStore, investigation: RepositoryInvestigation, qa_result: QAResult, changed_files: list[str]) -> str:
    criteria = task_store.planner_brief.acceptance_criteria if task_store.planner_brief else []
    tests = [run.command for run in qa_result.test_runs]
    trail = [
        "## Analysis",
        task_store.planner_brief.issue_summary if task_store.planner_brief else issue.title,
        "",
        "## Fix strategy",
        task_store.planner_brief.fix_strategy if task_store.planner_brief else "Not recorded.",
        "",
        "## Candidate files from deterministic search",
        *[f"- `{candidate.path}` score={candidate.score}" for candidate in investigation.candidate_files[:10]],
        "",
        "## Task execution summary",
        *[f"- {task.id}: {task.status} — {task.title}" for task in task_store.tasks],
        "",
        "## QA result",
        f"Passed: {qa_result.passed}",
        "",
        "## Coverage report",
        "```text",
        qa_result.coverage_report,
        "```",
    ]
    return build_pr_body(
        issue=issue,
        acceptance_criteria=criteria,
        files_changed=changed_files,
        tests_run=tests,
        decision_trail="\n".join(trail),
    )


def _set_authenticated_origin(repo: GitRepository, issue: GitHubIssue) -> None:
    if not os.getenv("GITHUB_TOKEN"):
        return
    repo.git(["remote", "set-url", "origin", issue.repository.https_url], check=False)
    # Use an in-memory extra header for push instead of persisting the token in .git/config.
    # GitHub accepts the x-access-token username through credential helpers if configured;
    # otherwise users can set origin manually. We avoid storing secrets in the repo.
