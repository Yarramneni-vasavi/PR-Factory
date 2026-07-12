from __future__ import annotations

import argparse
import os

from pr_factory.github_tool import DEFAULT_GITHUB_API_URL


def normalize_issue_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return candidate

    key, separator, rest = candidate.partition("=")
    if separator and key.strip().lower() in {"issue_url", "issue-url", "url", "issue"}:
        stripped_rest = rest.strip()
        return stripped_rest or candidate

    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch and print details for a GitHub issue URL.",
    )
    parser.add_argument(
        "issue_url",
        nargs="?",
        help="GitHub issue URL, for example https://github.com/owner/repo/issues/123",
    )
    parser.add_argument(
        "--issue-url",
        dest="issue_url_opt",
        help="GitHub issue URL (alternative to the positional argument).",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API_URL),
        help="GitHub API base URL. Defaults to https://api.github.com or GITHUB_API_URL.",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="Fetch only the issue body, without comments.",
    )
    return parser

