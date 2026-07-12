from __future__ import annotations

import json
from typing import Any

from pr_factory.config import signal_agent_model
from pr_factory.cli.formatters import format_issue


def issue_signal_prompt(issue) -> str:
    return f"""
You are the PR Factory issue triage agent.

Read the GitHub issue details below and decide whether PR Factory should analyze it as a bug.

Discard the issue if comments or issue text indicate it is not a bug, already classified as a feature request, or already classified as an enhancement request. Examples of discard signals include: "not a bug", "working as intended", "intended behavior", "feature request", "enhancement", "needs product decision", or a maintainer saying this should not be fixed as a bug.

If it is a genuine bug report to analyze, extract useful investigation signals.

Return only strict JSON with this schema:
{{
  "proceed": true,
  "classification": "bug",
  "discard_reason": null,
  "summary": "one sentence issue summary",
  "signals": {{
    "error_messages": [],
    "stack_traces": [],
    "file_paths": [],
    "symbols": [],
    "routes_or_endpoints": [],
    "commands": [],
    "test_names": [],
    "reproduction_steps": [],
    "expected_behavior": null,
    "actual_behavior": null,
    "keywords": []
  }}
}}

If discarded, return:
{{
  "proceed": false,
  "classification": "not_bug" | "feature" | "enhancement",
  "discard_reason": "specific reason based on issue/comments",
  "summary": "one sentence summary",
  "signals": {{
    "error_messages": [],
    "stack_traces": [],
    "file_paths": [],
    "symbols": [],
    "routes_or_endpoints": [],
    "commands": [],
    "test_names": [],
    "reproduction_steps": [],
    "expected_behavior": null,
    "actual_behavior": null,
    "keywords": []
  }}
}}

GitHub issue details:
{format_issue(issue)}
""".strip()


def parse_agent_json(response: str) -> dict[str, Any]:
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("agent response did not contain a JSON object")

    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("agent response JSON must be an object")
    if not isinstance(data.get("proceed"), bool):
        raise ValueError("agent response JSON must include boolean 'proceed'")
    if "signals" not in data or not isinstance(data["signals"], dict):
        raise ValueError("agent response JSON must include object 'signals'")
    return data


def analyze_issue_signals(issue) -> dict[str, Any]:
    from run_agent import AIAgent

    agent = AIAgent(
        model=signal_agent_model(),
        quiet_mode=True,
        enabled_toolsets=[],
    )
    response = agent.chat(issue_signal_prompt(issue))
    return parse_agent_json(response)

