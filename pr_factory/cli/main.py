from __future__ import annotations

import json
import sys
from typing import Sequence

from pr_factory.cli.args import build_parser, normalize_issue_url
from pr_factory.cli.formatters import (
    format_clone_result,
    format_issue,
    format_issue_status_result,
    format_publish_result,
    format_qa_result,
    format_repository_investigation,
    format_signal_analysis,
    format_task_store,
    format_vector_context,
)
from pr_factory.agent_workflow import run_planner_coder_workflow
from pr_factory.config import load_dotenv
from pr_factory.github_tool import GitCommandError, GitHubApiError, GitHubClient
from pr_factory.issue_signals import analyze_issue_signals
from pr_factory.observability import get_logger
from pr_factory.context.vector_context import retrieve_vector_context
from pr_factory.publisher import publish_fix
from pr_factory.qa import run_qa
from pr_factory.repo_investigation import get_or_detect_project_stack, investigate_repository
from pr_factory.repository import clone_or_update_repository, prepare_issue_branch
from pr_factory.sanitize import sanitize_git_error

logger = get_logger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args(argv)

    raw_issue_url = args.issue_url_opt or args.issue_url or input("GitHub issue URL: ").strip()
    issue_url = normalize_issue_url(raw_issue_url)
    if not issue_url:
        parser.error("issue_url is required")
    logger.info("Starting PR Factory run for issue_url=%s", issue_url)

    client = GitHubClient(api_url=args.api_url)
    try:
        issue = client.get_issue_from_url(issue_url, include_comments=not args.no_comments)
        logger.info("Fetched issue %s#%s state=%s", issue.repository.full_name, issue.number, issue.state)
    except ValueError as error:
        print(f"Invalid GitHub issue URL: {error}", file=sys.stderr)
        return 2
    except GitHubApiError as error:
        print(f"Failed to fetch GitHub issue: {error}", file=sys.stderr)
        return 1

    if issue.state.lower() != "open":
        logger.info("Skipping non-open issue %s#%s", issue.repository.full_name, issue.number)
        print(format_issue(issue))
        print(format_issue_status_result(issue))
        return 0

    try:
        signal_analysis = analyze_issue_signals(issue)
    except (ImportError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(format_issue(issue))
        print(f"Failed to analyze issue signals: {error}", file=sys.stderr)
        return 1

    if not signal_analysis["proceed"]:
        logger.info("Skipping issue after triage classification=%s", signal_analysis.get("classification"))
        print(format_issue(issue))
        print(format_signal_analysis(signal_analysis))
        print("Skipping repository clone.")
        return 0

    try:
        repo, clone_action = clone_or_update_repository(issue.repository)
        logger.info("Repository %s clone action=%s path=%s", issue.repository.full_name, clone_action, repo.path)
        branch = prepare_issue_branch(repo, issue.number, issue.title)
        logger.info("Prepared work branch %s", branch)
    except GitCommandError as error:
        print(format_issue(issue))
        print(f"Failed to clone or update repository: {sanitize_git_error(error)}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(format_issue(issue))
        print(f"Failed to clone or update repository: {error}", file=sys.stderr)
        return 1

    print(format_issue(issue))
    print(format_signal_analysis(signal_analysis))
    print(format_clone_result(issue.repository, repo, clone_action))
    stack = get_or_detect_project_stack(repo.path, refresh=clone_action == "cloned")
    investigation = investigate_repository(repo.path, signal_analysis, stack)
    vector_context = retrieve_vector_context(
        repo_path=repo.path,
        repo_name=issue.repository.full_name,
        commit=None,
        investigation=investigation,
    )
    logger.info("Repository investigation found %s candidates and %s tests", len(investigation.candidate_files), len(investigation.relevant_tests))
    print(format_repository_investigation(investigation))
    print(format_vector_context(vector_context))
    try:
        task_store = run_planner_coder_workflow(
            issue=issue,
            issue_url=issue_url,
            repo_path=str(repo.path),
            signal_analysis=signal_analysis,
            investigation=investigation,
            vector_context=vector_context,
        )
    except RuntimeError as error:
        print(f"Failed to run planner/coder agents: {error}", file=sys.stderr)
        return 1

    print(format_task_store(task_store))
    if not task_store.all_done():
        print("\nQA / Coverage\n=============\nSkipped: coder tasks are not all completed.")
        print("\nGitHub Pull Request\n===================\nSkipped: coder tasks are not all completed.")
        logger.info("Skipping QA and PR because coder tasks are incomplete")
        return 0

    qa_result = run_qa(repo.path, task_store, stack)
    print(format_qa_result(qa_result))

    try:
        publish_result = publish_fix(
            repo=repo,
            issue=issue,
            task_store=task_store,
            investigation=investigation,
            qa_result=qa_result,
            branch=branch,
            github_client=client,
        )
    except (GitCommandError, GitHubApiError, RuntimeError) as error:
        print(f"Failed to publish pull request: {sanitize_git_error(error) if isinstance(error, GitCommandError) else error}", file=sys.stderr)
        return 1

    print(format_publish_result(publish_result))
    logger.info("Completed PR Factory run for issue_url=%s", issue_url)
    return 0

