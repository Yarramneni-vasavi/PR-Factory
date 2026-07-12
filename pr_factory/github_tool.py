"""GitHub and git operations for PR Factory.

This module is intentionally dependency-light so Phase 1 can run from a cloned
repository without requiring a vector database or GitHub CLI installation.

It provides two layers:
- GitHubClient: reads issues/comments and creates pull requests through the
  GitHub REST API using ``GITHUB_TOKEN``.
- GitRepository: wraps local git operations used by the coder/QA flow.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_GITHUB_API_URL = "https://api.github.com"
ISSUE_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)(?:[/?#].*)?$"
)


class GitHubToolError(RuntimeError):
    """Base error raised by this module."""


class GitCommandError(GitHubToolError):
    """Raised when a git command fails and check=True."""

    def __init__(self, result: "CommandResult") -> None:
        self.result = result
        message = (
            f"git command failed with exit code {result.returncode}: "
            f"{' '.join(result.command)}\n{result.stderr or result.stdout}"
        )
        super().__init__(message)


class GitHubApiError(GitHubToolError):
    """Raised when the GitHub API returns an error."""


@dataclass(frozen=True)
class RepositoryRef:
    """A GitHub repository reference."""

    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def https_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}.git"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


@dataclass(frozen=True)
class GitHubIssue:
    """GitHub issue data needed by planner/coder agents."""

    repository: RepositoryRef
    number: int
    title: str
    body: str
    state: str
    labels: list[str]
    user: str | None
    html_url: str
    comments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        """Return title/body/comments as a single investigation text block."""

        parts = [f"Title: {self.title}", f"Body:\n{self.body or ''}"]
        for index, comment in enumerate(self.comments, start=1):
            author = comment.get("user", {}).get("login", "unknown")
            body = comment.get("body") or ""
            parts.append(f"Comment {index} by {author}:\n{body}")
        return "\n\n".join(parts)


@dataclass(frozen=True)
class PullRequest:
    """Created pull request details."""

    number: int
    html_url: str
    state: str
    title: str


@dataclass(frozen=True)
class CommandResult:
    """Result from a local git command."""

    command: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class ConflictStatus:
    """Current merge/rebase conflict state."""

    has_conflicts: bool
    files: list[str]
    operation: str | None


def parse_github_issue_url(issue_url: str) -> tuple[RepositoryRef, int]:
    """Parse a GitHub issue URL into a repository ref and issue number."""

    match = ISSUE_URL_RE.match(issue_url.strip())
    if not match:
        raise ValueError(f"Not a supported GitHub issue URL: {issue_url}")
    repo = RepositoryRef(owner=match.group("owner"), repo=match.group("repo"))
    return repo, int(match.group("number"))


class GitHubClient:
    """Small GitHub REST API client for issue and pull request operations."""

    def __init__(
        self,
        token: str | None = None,
        api_url: str = DEFAULT_GITHUB_API_URL,
        timeout_seconds: int = 30,
    ) -> None:
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_issue_from_url(self, issue_url: str, include_comments: bool = True) -> GitHubIssue:
        """Read a GitHub issue and optionally its comments from an issue URL."""

        repository, number = parse_github_issue_url(issue_url)
        return self.get_issue(repository, number, include_comments=include_comments)

    def get_issue(
        self,
        repository: RepositoryRef,
        number: int,
        include_comments: bool = True,
    ) -> GitHubIssue:
        """Read a GitHub issue by repository and issue number."""

        issue = self._request_json("GET", f"/repos/{repository.full_name}/issues/{number}")
        comments: list[dict[str, Any]] = []
        if include_comments and issue.get("comments", 0):
            comments = self._request_json(
                "GET",
                f"/repos/{repository.full_name}/issues/{number}/comments",
            )

        return GitHubIssue(
            repository=repository,
            number=number,
            title=issue.get("title") or "",
            body=issue.get("body") or "",
            state=issue.get("state") or "unknown",
            labels=[label.get("name", "") for label in issue.get("labels", [])],
            user=(issue.get("user") or {}).get("login"),
            html_url=issue.get("html_url") or f"{repository.web_url}/issues/{number}",
            comments=comments,
        )

    def create_pull_request(
        self,
        repository: RepositoryRef,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
    ) -> PullRequest:
        """Create a pull request after QA has passed."""

        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }
        data = self._request_json("POST", f"/repos/{repository.full_name}/pulls", payload)
        return PullRequest(
            number=int(data["number"]),
            html_url=data["html_url"],
            state=data.get("state", "unknown"),
            title=data.get("title", title),
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.api_url}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "pr-factory-github-tool",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            raise GitHubApiError(f"GitHub API {method} {url} failed: {error.code} {error_body}") from error
        except urllib.error.URLError as error:
            raise GitHubApiError(f"GitHub API {method} {url} failed: {error}") from error

        if not raw:
            return None
        return json.loads(raw)


class GitRepository:
    """Local git operations used by PR Factory agents."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    @classmethod
    def clone(
        cls,
        repo_url: str,
        destination: str | Path,
        branch: str | None = None,
        depth: int | None = None,
    ) -> "GitRepository":
        """Clone a repository and return a local GitRepository wrapper."""

        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone"]
        if branch:
            command.extend(["--branch", branch])
        if depth:
            command.extend(["--depth", str(depth)])
        command.extend([repo_url, str(destination_path)])
        _run(command, cwd=destination_path.parent, check=True)
        return cls(destination_path)

    def fetch(self, remote: str = "origin", prune: bool = True) -> CommandResult:
        command = ["git", "fetch", remote]
        if prune:
            command.append("--prune")
        return self.git(command[1:])

    def current_branch(self) -> str:
        result = self.git(["branch", "--show-current"])
        return result.stdout.strip()

    def default_branch(self, remote: str = "origin") -> str:
        """Return the remote default branch name, falling back to main/master."""

        result = self.git(["symbolic-ref", f"refs/remotes/{remote}/HEAD"], check=False)
        if result.ok:
            return result.stdout.strip().split("/")[-1]
        for candidate in ("main", "master"):
            if self.git(["rev-parse", "--verify", f"{remote}/{candidate}"], check=False).ok:
                return candidate
        return "main"

    def checkout(self, branch: str, create: bool = False, start_point: str | None = None) -> CommandResult:
        command = ["checkout"]
        if create:
            command.append("-b")
        command.append(branch)
        if start_point:
            command.append(start_point)
        return self.git(command)

    def checkout_new_branch(self, branch: str, start_point: str = "HEAD") -> CommandResult:
        return self.checkout(branch, create=True, start_point=start_point)

    def status(self, porcelain: bool = True) -> str:
        command = ["status"]
        if porcelain:
            command.append("--porcelain")
        return self.git(command).stdout

    def is_clean(self) -> bool:
        return not self.status(porcelain=True).strip()

    def add(self, paths: Sequence[str] | str = ".") -> CommandResult:
        normalized = [paths] if isinstance(paths, str) else list(paths)
        return self.git(["add", *normalized])

    def commit(self, message: str, allow_empty: bool = False) -> CommandResult:
        command = ["commit", "-m", message]
        if allow_empty:
            command.append("--allow-empty")
        return self.git(command)

    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        set_upstream: bool = True,
        force_with_lease: bool = False,
    ) -> CommandResult:
        branch = branch or self.current_branch()
        command = ["push"]
        if set_upstream:
            command.append("-u")
        if force_with_lease:
            command.append("--force-with-lease")
        command.extend([remote, branch])
        return self.git(command)

    def pull_rebase(self, remote: str = "origin", branch: str | None = None) -> CommandResult:
        branch = branch or self.current_branch()
        return self.git(["pull", "--rebase", remote, branch], check=False)

    def rebase(self, upstream: str, autostash: bool = True) -> CommandResult:
        command = ["rebase"]
        if autostash:
            command.append("--autostash")
        command.append(upstream)
        return self.git(command, check=False)

    def continue_rebase(self) -> CommandResult:
        return self.git(["rebase", "--continue"], check=False)

    def abort_rebase(self) -> CommandResult:
        return self.git(["rebase", "--abort"], check=False)

    def conflict_status(self) -> ConflictStatus:
        files = self.conflict_files()
        operation = self._current_operation()
        return ConflictStatus(has_conflicts=bool(files), files=files, operation=operation)

    def conflict_files(self) -> list[str]:
        result = self.git(["diff", "--name-only", "--diff-filter=U"], check=False)
        if not result.ok:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    def resolve_conflict_with_strategy(self, paths: Sequence[str] | str, strategy: str) -> CommandResult:
        """Resolve conflicted files using a mechanical strategy.

        ``strategy`` must be ``ours`` or ``theirs``. For semantic conflict
        resolution, have a coder edit the files manually and call ``mark_resolved``.
        """

        if strategy not in {"ours", "theirs"}:
            raise ValueError("strategy must be 'ours' or 'theirs'")
        normalized = [paths] if isinstance(paths, str) else list(paths)
        checkout = self.git(["checkout", f"--{strategy}", "--", *normalized], check=False)
        if not checkout.ok:
            return checkout
        return self.mark_resolved(normalized)

    def mark_resolved(self, paths: Sequence[str] | str) -> CommandResult:
        return self.add(paths)

    def create_worktree(self, path: str | Path, branch: str, start_point: str = "HEAD") -> "GitRepository":
        worktree_path = Path(path).resolve()
        self.git(["worktree", "add", "-b", branch, str(worktree_path), start_point])
        return GitRepository(worktree_path)

    def remove_worktree(self, path: str | Path, force: bool = False) -> CommandResult:
        command = ["worktree", "remove"]
        if force:
            command.append("--force")
        command.append(str(Path(path).resolve()))
        return self.git(command)

    def changed_files(self, base_ref: str = "HEAD") -> list[str]:
        result = self.git(["diff", "--name-only", base_ref], check=False)
        if not result.ok:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    def diff(self, base_ref: str = "HEAD") -> str:
        return self.git(["diff", base_ref], check=False).stdout

    def git(self, args: Sequence[str], check: bool = True) -> CommandResult:
        return _run(["git", *args], cwd=self.path, check=check)

    def _current_operation(self) -> str | None:
        git_dir_result = self.git(["rev-parse", "--git-dir"], check=False)
        if not git_dir_result.ok:
            return None
        git_dir = Path(git_dir_result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = self.path / git_dir
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            return "rebase"
        if (git_dir / "MERGE_HEAD").exists():
            return "merge"
        if (git_dir / "CHERRY_PICK_HEAD").exists():
            return "cherry-pick"
        return None


def build_pr_body(
    issue: GitHubIssue,
    acceptance_criteria: Iterable[str],
    files_changed: Iterable[str],
    tests_run: Iterable[str],
    decision_trail: str,
) -> str:
    """Build a PR body that carries the Phase 1 decision trail."""

    criteria = "\n".join(f"- {item}" for item in acceptance_criteria) or "- Not recorded"
    files = "\n".join(f"- `{path}`" for path in files_changed) or "- Not recorded"
    tests = "\n".join(f"- `{command}`" for command in tests_run) or "- Not recorded"
    return (
        f"Fixes {issue.html_url}\n\n"
        "## Issue summary\n"
        f"{issue.title}\n\n"
        "## Acceptance criteria\n"
        f"{criteria}\n\n"
        "## Files changed\n"
        f"{files}\n\n"
        "## Tests run\n"
        f"{tests}\n\n"
        "## Decision trail\n"
        f"{decision_trail}\n"
    )


def authenticated_clone_url(repository: RepositoryRef, token: str | None = None) -> str:
    """Return a GitHub HTTPS clone URL with an optional token embedded.

    Use this only for subprocess clone/push. Never log the returned URL.
    """

    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        return repository.https_url
    encoded = urllib.parse.quote(token, safe="")
    return f"https://x-access-token:{encoded}@github.com/{repository.owner}/{repository.repo}.git"


def _run(command: Sequence[str], cwd: str | Path, check: bool = True) -> CommandResult:
    cwd_path = Path(cwd).resolve()
    completed = subprocess.run(
        list(command),
        cwd=str(cwd_path),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result = CommandResult(
        command=tuple(command),
        cwd=cwd_path,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and not result.ok:
        raise GitCommandError(result)
    return result
