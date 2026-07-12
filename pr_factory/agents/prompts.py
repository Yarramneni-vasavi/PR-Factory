from __future__ import annotations

import json
from typing import Any

from pr_factory.agents.json_utils import model_json_schema_text
from pr_factory.agents.schemas import CoderInput, CoderResult, PlannerBrief, PlannerInput


PLANNER_SYSTEM_PROMPT = """You are PR Factory's planner agent.
You receive a GitHub issue, extracted signals, project stack metadata, deterministic search results, and relevant tests.
Produce a precise fix brief for a coder. Do not invent files or APIs. Use only the provided evidence.
Prefer the smallest safe change that satisfies the issue. Include acceptance criteria and verification commands.
Return only JSON that conforms to the requested schema."""


CODER_SYSTEM_PROMPT = """You are PR Factory's coder agent.
You receive a planner brief and repository investigation context.
Create an implementation plan a code-editing worker can execute. Do not claim files were changed or tests passed.
Inspect listed files first, make the smallest fix, add/update tests when needed, and run focused tests before broader tests.
Return only JSON that conforms to the requested schema."""


def render_planner_prompt(payload: PlannerInput, skills_text: str = "") -> str:
    sections = [PLANNER_SYSTEM_PROMPT]
    if skills_text.strip():
        sections.extend(["Planner skills:", skills_text.strip()])
    sections.extend(
        [
            "Output schema:",
            model_json_schema_text(PlannerBrief),
            "Input:",
            payload.model_dump_json(indent=2),
        ]
    )
    return "\n\n".join(sections)


def render_coder_prompt(payload: CoderInput) -> str:
    return "\n\n".join(
        [
            CODER_SYSTEM_PROMPT,
            "Output schema:",
            model_json_schema_text(CoderResult),
            "Input:",
            payload.model_dump_json(indent=2),
        ]
    )


def langchain_messages(system_prompt: str, user_prompt: str) -> list[tuple[str, str]]:
    return [("system", system_prompt), ("user", user_prompt)]


def compact_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)
