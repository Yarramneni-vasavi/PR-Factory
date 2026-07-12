from __future__ import annotations

from typing import Any

from pr_factory.agents.json_utils import coerce_structured_response
from pr_factory.agents.llm import build_langchain_chat_model
from pr_factory.agents.schemas import PlannerBrief, PlannerInput
from pr_factory.agents.prompts import PLANNER_SYSTEM_PROMPT, render_planner_prompt
from pr_factory.agents.skills import DEFAULT_SKILLS_DIR, load_planner_skills


class PlannerAgent:
    """Create a focused fix brief from issue and repository evidence.

    The planner turns extracted issue signals, project stack metadata,
    deterministic search results, and relevant tests into acceptance criteria,
    suspected root cause, fix strategy, and files the coder should inspect.
    """

    def __init__(self, llm: Any | None = None, skills_dir: str | None = None) -> None:
        self.llm = llm or build_langchain_chat_model()
        self.skills_dir = skills_dir or str(DEFAULT_SKILLS_DIR)

    def plan(self, planner_input: PlannerInput) -> PlannerBrief:
        prompt = render_planner_prompt(planner_input, skills_text=load_planner_skills(self.skills_dir))
        return _invoke_structured(self.llm, prompt, PlannerBrief)

    def system_prompt(self) -> str:
        return PLANNER_SYSTEM_PROMPT


def _invoke_structured(llm: Any, prompt: str, schema: type[PlannerBrief]) -> PlannerBrief:
    if hasattr(llm, "with_structured_output"):
        structured_llm = llm.with_structured_output(schema)
        response = structured_llm.invoke(prompt)
    else:
        response = llm.invoke(prompt)
    return coerce_structured_response(response, schema)
