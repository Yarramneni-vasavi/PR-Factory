import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pr_factory.agents.code_worker import apply_coder_result, build_code_worker_prompt
from pr_factory.agents.schemas import CoderInput, CoderResult, PlannerBrief


class CodeWorkerTests(unittest.TestCase):
    def test_build_code_worker_prompt_contains_repo_task_and_plan(self):
        coder_input = self._coder_input()
        coder_result = self._coder_result()

        prompt = build_code_worker_prompt(coder_input, coder_result)

        self.assertIn("Modify files directly", prompt)
        self.assertIn("task-001", prompt)
        self.assertIn("src/AuthProvider.tsx", prompt)

    def test_apply_coder_result_runs_worker_and_marks_applied(self):
        coder_input = self._coder_input()
        coder_result = self._coder_result()
        old_apply = os.environ.get("PR_FACTORY_CODER_APPLY")
        old_command = os.environ.get("PR_FACTORY_CODER_COMMAND")
        os.environ["PR_FACTORY_CODER_APPLY"] = "true"
        os.environ["PR_FACTORY_CODER_COMMAND"] = "python-agent"
        try:
            with patch("pr_factory.agents.code_worker.subprocess.run") as run:
                run.return_value = SimpleNamespace(returncode=0, stdout="changed files", stderr="")

                updated = apply_coder_result(coder_input, coder_result)

            self.assertTrue(updated.applied)
            self.assertIn("changed files", updated.worker_output)
            self.assertEqual(run.call_args.kwargs["cwd"], str(Path(coder_input.repo_path).resolve()))
            self.assertEqual(run.call_args.args[0][0], os.sys.executable)
            self.assertTrue(run.call_args.args[0][-1].endswith(".md"))
        finally:
            self._restore_env("PR_FACTORY_CODER_APPLY", old_apply)
            self._restore_env("PR_FACTORY_CODER_COMMAND", old_command)

    @staticmethod
    def _restore_env(key, value):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    @staticmethod
    def _coder_input():
        brief = PlannerBrief(
            issue_summary="Bug",
            acceptance_criteria=["Done"],
            relevant_files=[],
            fix_strategy="Fix",
            tests_to_run=[],
        )
        return CoderInput(
            repo_path=".",
            planner_brief=brief,
            project_stack={},
            candidate_files=[{"path": "src/AuthProvider.tsx"}],
            vector_context=[{"path": "src/AuthProvider.tsx", "content": "function AuthProvider() {}"}],
            relevant_tests=[],
            task_id="task-001",
            task_title="Handle AuthProvider",
            task_focus={"path": "src/AuthProvider.tsx"},
        )

    @staticmethod
    def _coder_result():
        return CoderResult(
            summary="Plan",
            file_change_plan=[
                {
                    "path": "src/AuthProvider.tsx",
                    "action": "modify",
                    "reason": "Fix bug",
                    "instructions": "Edit file",
                }
            ],
            commands_to_run=[],
            tests_to_run=[],
            success_criteria=["Done"],
        )


if __name__ == "__main__":
    unittest.main()
