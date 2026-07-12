import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pr_factory.agents.schemas import PlannerBrief
from pr_factory.github_tool import GitHubIssue, RepositoryRef
from pr_factory.publisher import build_pull_request_body, changed_working_files, publish_fix
from pr_factory.qa import CommandRun, QAResult, run_qa
from pr_factory.repo_investigation import CandidateFile, ProjectStack, RepositoryInvestigation
from pr_factory.task_store import TaskStore


class FakeRepo:
    def __init__(self):
        self.added = None
        self.committed = None
        self.pushed = False
        self._status = " M src/app.py\n?? .pr-factory/tasks/issue-1.json\n?? tests/test_app.py\n"

    def git(self, args, check=True):
        if args == ["status", "--porcelain"]:
            return SimpleResult(stdout=self._status)
        return SimpleResult(stdout="")

    def add(self, files):
        self.added = files
        return SimpleResult(stdout="")

    def commit(self, message, allow_empty=False):
        self.committed = message
        return SimpleResult(stdout="")

    def push(self, branch=None):
        self.pushed = True
        return SimpleResult(stdout="")

    def default_branch(self):
        return "main"


class SimpleResult:
    def __init__(self, stdout="", stderr="", ok=True):
        self.stdout = stdout
        self.stderr = stderr
        self.ok = ok


class FakeClient:
    def __init__(self):
        self.created = None

    def create_pull_request(self, **kwargs):
        self.created = kwargs
        return type("PR", (), {"number": 1, "html_url": "https://github.com/acme/widgets/pull/1", "state": "open", "title": kwargs["title"]})()


class PublishAndQATests(unittest.TestCase):
    def test_changed_working_files_excludes_pr_factory_store(self):
        self.assertEqual(changed_working_files(FakeRepo()), ["src/app.py", "tests/test_app.py"])

    def test_publish_fix_commits_pushes_and_creates_pr(self):
        repo = FakeRepo()
        client = FakeClient()
        issue = self._issue()
        with tempfile.TemporaryDirectory(prefix="publish-test-") as tmp:
            store = TaskStore.for_issue(tmp, issue)
            store.set_planner_brief(self._brief())
            qa = QAResult(passed=True, test_runs=[CommandRun("pytest", 0, "ok", "")], coverage_run=CommandRun("coverage", 0, "TOTAL 90%", ""))
            investigation = RepositoryInvestigation(ProjectStack(), [], [CandidateFile("src/app.py", 1)], [])

            result = publish_fix(repo=repo, issue=issue, task_store=store, investigation=investigation, qa_result=qa, branch="fix/issue-1", github_client=client)

        self.assertTrue(result.commit_created)
        self.assertTrue(result.pushed)
        self.assertEqual(repo.added, ["src/app.py", "tests/test_app.py"])
        self.assertIn("Fix issue #1", repo.committed)
        self.assertEqual(result.pull_request.html_url, "https://github.com/acme/widgets/pull/1")
        self.assertIn("TOTAL 90%", client.created["body"])

    def test_publish_blocks_when_qa_fails(self):
        issue = self._issue()
        with tempfile.TemporaryDirectory(prefix="publish-test-") as tmp:
            store = TaskStore.for_issue(tmp, issue)
            qa = QAResult(passed=False, test_runs=[CommandRun("pytest", 1, "", "fail")])
            result = publish_fix(repo=FakeRepo(), issue=issue, task_store=store, investigation=RepositoryInvestigation(ProjectStack(), [], [], []), qa_result=qa, branch="fix/issue-1", github_client=FakeClient())
        self.assertEqual(result.skipped_reason, "QA failed; PR creation blocked.")

    def test_run_qa_collects_tests_and_coverage(self):
        issue = self._issue()
        with tempfile.TemporaryDirectory(prefix="qa-test-") as tmp, patch("pr_factory.qa.subprocess.run") as run:
            store = TaskStore.for_issue(tmp, issue)
            store.set_planner_brief(self._brief())
            run.side_effect = [
                type("Completed", (), {"returncode": 0, "stdout": "tests ok", "stderr": ""})(),
                type("Completed", (), {"returncode": 0, "stdout": "TOTAL 88%", "stderr": ""})(),
            ]

            result = run_qa(tmp, store, ProjectStack(languages=["Python"], source_dirs=["src"], test_commands=[]))

        self.assertTrue(result.passed)
        self.assertIn("TOTAL 88%", result.coverage_report)

    @staticmethod
    def _issue():
        return GitHubIssue(RepositoryRef("acme", "widgets"), 1, "Bug", "Body", "open", ["bug"], "octocat", "https://github.com/acme/widgets/issues/1", [])

    @staticmethod
    def _brief():
        return PlannerBrief(issue_summary="Bug", acceptance_criteria=["Done"], relevant_files=[], fix_strategy="Fix", tests_to_run=["pytest"])


if __name__ == "__main__":
    unittest.main()
