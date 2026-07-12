import tempfile
import unittest
from pathlib import Path

from pr_factory.agent_workflow import run_planner_coder_workflow
from pr_factory.agents.schemas import CoderResult, PlannerBrief
from pr_factory.github_tool import GitHubIssue, RepositoryRef
from pr_factory.repo_investigation import CandidateFile, ProjectStack, RepositoryInvestigation
from pr_factory.task_store import TaskStore


class FakePlannerAgent:
    def __init__(self):
        self.calls = 0

    def plan(self, planner_input):
        self.calls += 1
        return PlannerBrief(
            issue_summary="Save crashes with token TypeError.",
            acceptance_criteria=["Save no longer crashes"],
            relevant_files=[
                {
                    "path": "src/AuthProvider.tsx",
                    "reason": "Matched AuthProvider and token error.",
                    "priority": "high",
                    "expected_change": "Add minimal guard.",
                },
                {
                    "path": "tests/AuthProvider.test.tsx",
                    "reason": "Relevant focused test.",
                    "priority": "medium",
                    "expected_change": "Cover token crash.",
                },
            ],
            suspected_root_cause="Token read before session is ready.",
            fix_strategy="Inspect relevant files and add smallest guard.",
            tests_to_run=["npm run test -- AuthProvider"],
        )


class FakeCoderAgent:
    def __init__(self):
        self.calls = []

    def execute(self, coder_input):
        self.calls.append(coder_input)
        return CoderResult(
            summary=f"Handled {coder_input.task_id}",
            file_change_plan=[
                {
                    "path": (coder_input.task_focus or {}).get("path", "src/AuthProvider.tsx"),
                    "action": "modify",
                    "reason": "Apply planner task.",
                    "instructions": "Inspect and make minimal change.",
                }
            ],
            commands_to_run=["npm run test -- AuthProvider"],
            tests_to_run=["npm run test -- AuthProvider"],
            success_criteria=["Focused test passes"],
        )


class ExplodingPlannerAgent:
    def plan(self, planner_input):
        raise AssertionError("planner should not run when brief is already stored")


class ExplodingCoderAgent:
    def execute(self, coder_input):
        raise AssertionError("coder should not run when tasks are already completed")


class AgentWorkflowTests(unittest.TestCase):
    def test_workflow_persists_planner_brief_and_completes_coder_tasks(self):
        with tempfile.TemporaryDirectory(prefix="workflow-test-") as tmp:
            issue = self._issue()
            planner = FakePlannerAgent()
            coder = FakeCoderAgent()

            store = run_planner_coder_workflow(
                issue=issue,
                issue_url=issue.html_url,
                repo_path=tmp,
                signal_analysis=self._analysis(),
                investigation=self._investigation(),
                vector_context=[{"path": "src/AuthProvider.tsx", "content": "vector chunk"}],
                planner_agent=planner,
                coder_agent=coder,
            )

            self.assertEqual(planner.calls, 1)
            self.assertEqual(len(coder.calls), 2)
            self.assertTrue(store.all_done())
            self.assertTrue(store.path.exists())
            self.assertEqual(store.summary_counts()["completed"], 2)
            self.assertEqual(coder.calls[0].task_id, "task-001")
            self.assertEqual(coder.calls[0].task_focus["path"], "src/AuthProvider.tsx")
            self.assertEqual(coder.calls[0].vector_context[0]["content"], "vector chunk")

            resumed = run_planner_coder_workflow(
                issue=issue,
                issue_url=issue.html_url,
                repo_path=tmp,
                signal_analysis=self._analysis(),
                investigation=self._investigation(),
                vector_context=[{"path": "src/AuthProvider.tsx", "content": "vector chunk"}],
                planner_agent=ExplodingPlannerAgent(),
                coder_agent=ExplodingCoderAgent(),
            )
            self.assertTrue(resumed.all_done())
            self.assertEqual(resumed.summary_counts()["completed"], 2)

    def test_task_store_recovers_running_tasks_to_pending(self):
        with tempfile.TemporaryDirectory(prefix="workflow-recovery-test-") as tmp:
            issue = self._issue()
            store = TaskStore.for_issue(tmp, issue)
            store.set_planner_brief(FakePlannerAgent().plan(None))
            task = store.claim_next_task()
            self.assertEqual(task.status, "running")

            recovered = TaskStore.for_issue(tmp, issue)

            self.assertEqual(recovered.summary_counts()["pending"], 2)
            self.assertEqual(recovered.tasks[0].error, "Recovered from interrupted running state.")

    def test_task_store_recovers_retryable_code_worker_failure(self):
        with tempfile.TemporaryDirectory(prefix="workflow-retry-test-") as tmp:
            issue = self._issue()
            store = TaskStore.for_issue(tmp, issue)
            store.set_planner_brief(FakePlannerAgent().plan(None))
            task = store.claim_next_task()
            store.fail_task(task.id, "[WinError 206] The filename or extension is too long")

            recovered = TaskStore.for_issue(tmp, issue)

            self.assertEqual(recovered.summary_counts()["pending"], 2)
            self.assertIn("Recovered retryable failure", recovered.tasks[0].error)

    @staticmethod
    def _issue():
        return GitHubIssue(
            repository=RepositoryRef("acme", "widgets"),
            number=7,
            title="Save crashes",
            body="TypeError: cannot read property token when saving.",
            state="open",
            labels=["bug"],
            user="octocat",
            html_url="https://github.com/acme/widgets/issues/7",
            comments=[],
        )

    @staticmethod
    def _analysis():
        return {"signals": {"symbols": ["AuthProvider"], "error_messages": ["TypeError"]}}

    @staticmethod
    def _investigation():
        stack = ProjectStack(languages=["TypeScript"], package_managers=["npm"], test_commands=["npm run test"])
        candidate = CandidateFile(path="src/AuthProvider.tsx", score=10, reasons=["content matched"], matched_terms=["AuthProvider"])
        return RepositoryInvestigation(
            stack=stack,
            search_terms=["AuthProvider", "TypeError"],
            candidate_files=[candidate],
            relevant_tests=["tests/AuthProvider.test.tsx"],
        )


if __name__ == "__main__":
    unittest.main()
