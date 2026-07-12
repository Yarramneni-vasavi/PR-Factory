from __future__ import annotations


def format_issue(issue) -> str:
    labels = ", ".join(issue.labels) if issue.labels else "none"
    author = issue.user or "unknown"
    body = issue.body.strip() if issue.body else "No body provided."

    lines = [
        "GitHub Issue Details",
        "====================",
        f"Repository: {issue.repository.full_name}",
        f"Issue: #{issue.number}",
        f"Title: {issue.title}",
        f"State: {issue.state}",
        f"Author: {author}",
        f"Labels: {labels}",
        f"URL: {issue.html_url}",
        "",
        "Body:",
        body,
        "",
        f"Comments: {len(issue.comments)}",
    ]

    for index, comment in enumerate(issue.comments, start=1):
        comment_author = comment.get("user", {}).get("login", "unknown")
        comment_body = (comment.get("body") or "").strip() or "No comment body provided."
        comment_url = comment.get("html_url")
        lines.extend(
            [
                "",
                f"Comment {index} by {comment_author}:",
                comment_body,
            ]
        )
        if comment_url:
            lines.append(f"Comment URL: {comment_url}")

    return "\n".join(lines)


def format_signal_analysis(analysis: dict) -> str:
    signals = analysis.get("signals", {})
    lines = [
        "",
        "Issue Signal Analysis",
        "=====================",
        f"Proceed: {analysis.get('proceed')}",
        f"Classification: {analysis.get('classification', 'unknown')}",
    ]
    if analysis.get("discard_reason"):
        lines.append(f"Discard reason: {analysis['discard_reason']}")
    if analysis.get("summary"):
        lines.append(f"Summary: {analysis['summary']}")

    for key in (
        "error_messages",
        "stack_traces",
        "file_paths",
        "symbols",
        "routes_or_endpoints",
        "commands",
        "test_names",
        "reproduction_steps",
        "keywords",
    ):
        values = signals.get(key) or []
        if values:
            lines.append("")
            lines.append(f"{key.replace('_', ' ').title()}:")
            lines.extend(f"- {value}" for value in values)

    for key in ("expected_behavior", "actual_behavior"):
        value = signals.get(key)
        if value:
            lines.append("")
            lines.append(f"{key.replace('_', ' ').title()}: {value}")

    return "\n".join(lines)


def format_clone_result(repository, repo, action: str) -> str:
    return "\n".join(
        [
            "",
            "Repository Clone",
            "================",
            f"Repository: {repository.full_name}",
            f"Action: {action}",
            f"Local path: {repo.path}",
        ]
    )


def format_repository_investigation(investigation) -> str:
    stack = investigation.stack
    lines = [
        "",
        "Repository Investigation",
        "========================",
        "Project Stack:",
        f"- Languages: {', '.join(stack.languages) if stack.languages else 'unknown'}",
        f"- Frameworks: {', '.join(stack.frameworks) if stack.frameworks else 'unknown'}",
        f"- Package managers: {', '.join(stack.package_managers) if stack.package_managers else 'unknown'}",
        f"- Dependency files: {', '.join(stack.dependency_files) if stack.dependency_files else 'none detected'}",
        f"- Source dirs: {', '.join(stack.source_dirs) if stack.source_dirs else 'none detected'}",
        f"- Test dirs: {', '.join(stack.test_dirs) if stack.test_dirs else 'none detected'}",
        f"- Test commands: {', '.join(stack.test_commands) if stack.test_commands else 'none detected'}",
        "",
        f"Search terms: {', '.join(investigation.search_terms) if investigation.search_terms else 'none'}",
        "",
        "Candidate Files:",
    ]

    if not investigation.candidate_files:
        lines.append("- none found")
    for candidate in investigation.candidate_files:
        terms = ", ".join(candidate.matched_terms)
        reasons = ", ".join(candidate.reasons)
        lines.append(f"- {candidate.path} (score {candidate.score}; {reasons}; terms: {terms})")
        for hit in candidate.hits[:3]:
            lines.append(f"  - L{hit.line}: {hit.preview}")

    lines.append("")
    lines.append("Relevant Tests:")
    if investigation.relevant_tests:
        lines.extend(f"- {path}" for path in investigation.relevant_tests)
    else:
        lines.append("- none found")

    return "\n".join(lines)


def format_vector_context(vector_context: list[dict]) -> str:
    lines = ["", "Qdrant Vector Context", "====================="]
    if not vector_context:
        lines.append("- none retrieved")
        return "\n".join(lines)
    for index, chunk in enumerate(vector_context, start=1):
        lines.append(
            f"- {index}. {chunk.get('path')}:{chunk.get('start_line')}-{chunk.get('end_line')} "
            f"semantic={float(chunk.get('semantic_score') or 0):.4f} "
            f"lexical={float(chunk.get('lexical_score') or 0):.4f} "
            f"combined={float(chunk.get('combined_score') or 0):.4f}"
        )
        preview = str(chunk.get("content") or "").replace("\n", " ")[:180]
        if preview:
            lines.append(f"  {preview}")
    return "\n".join(lines)


def format_task_store(store) -> str:
    counts = store.summary_counts()
    lines = [
        "",
        "Planner/Coder Task Store",
        "=========================",
        f"Path: {store.path}",
        f"Issue: #{store.issue_number}",
        f"Planner brief: {'present' if store.planner_brief else 'missing'}",
        "Tasks:",
        f"- pending: {counts['pending']}",
        f"- running: {counts['running']}",
        f"- completed: {counts['completed']}",
        f"- failed: {counts['failed']}",
    ]
    for task in store.tasks:
        lines.append(f"- {task.id}: {task.status} — {task.title}")
        if task.error:
            lines.append(f"  error: {task.error}")
    return "\n".join(lines)


def format_qa_result(qa_result) -> str:
    lines = ["", "QA / Coverage", "============="]
    lines.append(f"Passed: {qa_result.passed}")
    lines.append("Test commands:")
    for run in qa_result.test_runs:
        lines.append(f"- {run.command}: exit {run.returncode}")
    lines.append("Coverage:")
    lines.append(qa_result.coverage_report[:2000])
    return "\n".join(lines)


def format_publish_result(result) -> str:
    lines = ["", "GitHub Pull Request", "==================="]
    if result.skipped_reason:
        lines.append(f"Skipped: {result.skipped_reason}")
    lines.append(f"Branch: {result.branch or 'none'}")
    lines.append(f"Changed files: {', '.join(result.changed_files) if result.changed_files else 'none'}")
    lines.append(f"Commit created: {result.commit_created}")
    lines.append(f"Pushed: {result.pushed}")
    if result.pull_request:
        lines.append(f"PR: {result.pull_request.html_url}")
    return "\n".join(lines)


def format_issue_status_result(issue) -> str:
    return "\n".join(
        [
            "",
            "Issue Status",
            "============",
            f"State: {issue.state}",
            "Issue is already resolved. PR Factory only addresses open issues.",
            "Skipping repository clone.",
        ]
    )

