from __future__ import annotations

import os

from pr_factory.github_tool import GitCommandError


def sanitize_git_error(error: GitCommandError) -> str:
    text = error.result.stderr.strip() or error.result.stdout.strip() or f"exit code {error.result.returncode}"
    token = os.getenv("GITHUB_TOKEN")
    if token:
        text = text.replace(token, "***")

    marker = "x-access" + "-token" + ":"
    if marker in text:
        prefix, _, rest = text.partition(marker)
        _, at, suffix = rest.partition("@")
        text = prefix + marker + "***" + at + suffix

    return text

