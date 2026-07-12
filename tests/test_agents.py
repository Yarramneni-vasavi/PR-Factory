import tempfile
import unittest
from pathlib import Path

from pr_factory.agents import CoderAgent, PlannerAgent
from pr_factory.agents.prompts import render_coder_prompt, render_planner_prompt
from pr_factory.agents.schemas import CoderInput, CoderResult, PlannerBrief, PlannerInput
from pr_factory.agents.skills import load_planner_skills


class FakeStructuredLLM:
    def __init__(self, payload):
        self.payload = payload
        self.schema = None
        self.prompt = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        return self.schema.model_validate(self.payload)


class FakeTextLLM:
    def __init__(self, text):
        self.text = text
        self.prompt = None

    def invoke(self, prompt):
        self.prompt = prompt
        return self.text


class AgentTests(unittest.TestCase):
    def test_planner_agent_returns_structured_brief(self):
        planner_input = self._planner_input()
        payload = {
            "issue_summary": "Save crashes with token TypeError.",
            "acceptance_criteria": ["Save no longer crashes", "Focused auth test passes"],
            "relevant_files": [
                {
                    "path": "src/AuthProvider.tsx",
                    "reason": "Contains AuthProvider and token access from issue signals.",
                    "priority": "high",
                    "expected_change": "Guard token access or initialize session before save.",
                }
            ],
            "suspected_root_cause": "Session token is read before session exists.",
            "fix_strategy": "Inspect AuthProvider and add a minimal guard around token usage.",
            "tests_to_run": ["npm run test -- AuthProvider"],
            "risks": ["Could mask invalid auth state"],
            "decision_notes": ["Candidate file came from deterministic exact search."],
        }
        llm = FakeStructuredLLM(payload)

        brief = PlannerAgent(llm=llm).plan(planner_input)

        self.assertIsInstance(brief, PlannerBrief)
        self.assertEqual(brief.relevant_files[0].path, "src/AuthProvider.tsx")
        self.assertIn("Output schema", llm.prompt)
        self.assertIn("src/AuthProvider.tsx", llm.prompt)
        self.assertIn("Planner skills", llm.prompt)
        self.assertIn("Planner Code Investigation Skill", llm.prompt)

    def test_planner_agent_loads_skills_from_custom_directory(self):
        with tempfile.TemporaryDirectory(prefix="planner-skills-test-") as tmp:
            skills_dir = Path(tmp)
            (skills_dir / "custom-planning.md").write_text(
                "# Custom Planning Skill\n\nAlways cite exact search evidence.",
                encoding="utf-8",
            )
            llm = FakeStructuredLLM(
                {
                    "issue_summary": "Bug",
                    "acceptance_criteria": ["Done"],
                    "relevant_files": [],
                    "fix_strategy": "Fix",
                    "tests_to_run": [],
                }
            )

            PlannerAgent(llm=llm, skills_dir=str(skills_dir)).plan(self._planner_input())

            self.assertIn("Custom Planning Skill", llm.prompt)
            self.assertIn("Always cite exact search evidence", llm.prompt)

    def test_load_planner_skills_reads_markdown_files(self):
        with tempfile.TemporaryDirectory(prefix="planner-skills-loader-test-") as tmp:
            skills_dir = Path(tmp)
            (skills_dir / "a.md").write_text("# Skill A", encoding="utf-8")
            (skills_dir / "ignored.py").write_text("print('no')", encoding="utf-8")

            loaded = load_planner_skills(skills_dir)

            self.assertIn("Skill: a.md", loaded)
            self.assertIn("# Skill A", loaded)
            self.assertNotIn("ignored.py", loaded)

    def test_coder_agent_returns_structured_plan_from_text_json(self):
        planner_brief = PlannerBrief(
            issue_summary="Save crashes with token TypeError.",
            acceptance_criteria=["Save no longer crashes"],
            relevant_files=[
                {
                    "path": "src/AuthProvider.tsx",
                    "reason": "Token access occurs here.",
                    "priority": "high",
                    "expected_change": "Add guard.",
                }
            ],
            suspected_root_cause="Missing session guard.",
            fix_strategy="Add smallest guard and test.",
            tests_to_run=["npm run test -- AuthProvider"],
        )
        coder_input = CoderInput(
            repo_path="/tmp/repo",
            planner_brief=planner_brief,
            project_stack={"languages": ["TypeScript"], "test_commands": ["npm run test"]},
            candidate_files=[{"path": "src/AuthProvider.tsx"}],
            relevant_tests=["tests/AuthProvider.test.tsx"],
        )
        text = """```json
{
  "summary": "Modify AuthProvider and update focused test.",
  "file_change_plan": [
    {
      "path": "src/AuthProvider.tsx",
      "action": "modify",
      "reason": "Fix token crash",
      "instructions": "Inspect token access and add a minimal guard."
    }
  ],
  "commands_to_run": ["npm run test -- AuthProvider"],
  "tests_to_run": ["npm run test -- AuthProvider"],
  "success_criteria": ["Focused test passes"],
  "risks": [],
  "notes": ["Do not create PR from coder step"]
}
```"""
        llm = FakeTextLLM(text)

        result = CoderAgent(llm=llm).create_plan(coder_input)

        self.assertIsInstance(result, CoderResult)
        self.assertEqual(result.file_change_plan[0].path, "src/AuthProvider.tsx")
        self.assertIn("Output schema", llm.prompt)
        self.assertIn("planner_brief", llm.prompt)

    def test_prompt_renderers_include_context(self):
        planner_prompt = render_planner_prompt(self._planner_input())
        self.assertIn("project_stack", planner_prompt)
        self.assertIn("AuthProvider", planner_prompt)

        brief = PlannerBrief(
            issue_summary="Bug",
            acceptance_criteria=["Done"],
            relevant_files=[],
            fix_strategy="Fix",
            tests_to_run=[],
        )
        coder_prompt = render_coder_prompt(
            CoderInput(repo_path="/tmp/repo", planner_brief=brief, project_stack={}, candidate_files=[], relevant_tests=[])
        )
        self.assertIn("code-editing worker", coder_prompt)
        self.assertIn("/tmp/repo", coder_prompt)

    @staticmethod
    def _planner_input():
        return PlannerInput(
            issue_url="https://github.com/acme/widgets/issues/7",
            issue_title="Save crashes",
            issue_body="TypeError: cannot read property token when saving.",
            issue_comments=["I can reproduce this on main."],
            signal_analysis={
                "summary": "Save crashes with token TypeError.",
                "signals": {"symbols": ["AuthProvider"], "error_messages": ["TypeError"]},
            },
            project_stack={"languages": ["TypeScript"], "test_commands": ["npm run test"]},
            candidate_files=[{"path": "src/AuthProvider.tsx", "score": 12}],
            relevant_tests=["tests/AuthProvider.test.tsx"],
            repo_path="/tmp/repo",
        )


if __name__ == "__main__":
    unittest.main()
