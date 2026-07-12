from __future__ import annotations

import re
from pathlib import Path

from pr_factory.github_tool import GitRepository, RepositoryRef, authenticated_clone_url


def repository_clone_path(repository: RepositoryRef, projects_dir: Path | None = None) -> Path:
    root = projects_dir or Path.cwd() / ".projects"
    return root / repository.owner / repository.repo


def clone_or_update_repository(repository: RepositoryRef) -> tuple[GitRepository, str]:
    destination = repository_clone_path(repository)
    if (destination / ".git").exists():
        return GitRepository(destination), "already cloned"

    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"Clone destination exists and is not an empty git repository: {destination}")

    repo = GitRepository.clone(authenticated_clone_url(repository), destination)
    return repo, "cloned"


def prepare_issue_branch(repo: GitRepository, issue_number: int, issue_title: str) -> str:
    branch = f"pr-factory/issue-{issue_number}-{_slug(issue_title)}"[:100].rstrip("-")
    current = repo.current_branch()
    if current == branch:
        return branch

    if repo.git(["rev-parse", "--verify", branch], check=False).ok:
        repo.checkout(branch)
        return branch

    base = repo.default_branch()
    repo.fetch()
    start_point = f"origin/{base}"
    if not repo.git(["rev-parse", "--verify", start_point], check=False).ok:
        start_point = "HEAD"
    repo.checkout_new_branch(branch, start_point=start_point)
    return branch


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "fix"
