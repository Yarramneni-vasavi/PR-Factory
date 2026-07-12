from __future__ import annotations

from typing import Any

from pr_factory.agents.code_worker import apply_coder_result
from pr_factory.agents.json_utils import coerce_structured_response
from pr_factory.agents.llm import build_langchain_chat_model
from pr_factory.agents.prompts import CODER_SYSTEM_PROMPT, render_coder_prompt
from pr_factory.agents.schemas import CoderInput, CoderResult


class CoderAgent:
    """Prepare the implementation steps for a durable coder task.

    The coder consumes the planner brief and one task-store item, then returns
    the file-level change plan, commands to run, tests to execute, risks, and
    success criteria needed to implement and verify the fix.
    """

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or build_langchain_chat_model()

    def create_plan(self, coder_input: CoderInput) -> CoderResult:
        prompt = render_coder_prompt(coder_input)
        return _invoke_structured(self.llm, prompt, CoderResult)

    def execute(self, coder_input: CoderInput) -> CoderResult:
        """Run one task-store item and return its structured coder result."""

        coder_result = self.create_plan(coder_input)
        return apply_coder_result(coder_input, coder_result)

    def system_prompt(self) -> str:
        return CODER_SYSTEM_PROMPT


def _invoke_structured(llm: Any, prompt: str, schema: type[CoderResult]) -> CoderResult:
    if hasattr(llm, "with_structured_output"):
        structured_llm = llm.with_structured_output(schema)
        response = structured_llm.invoke(prompt)
    else:
        response = llm.invoke(prompt)
    return coerce_structured_response(response, schema)
