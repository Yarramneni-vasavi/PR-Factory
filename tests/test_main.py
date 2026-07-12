import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pr_factory.cli.args import build_parser, normalize_issue_url
from pr_factory.cli.main import main
from pr_factory.github_tool import GitHubIssue, RepositoryRef
from pr_factory.issue_signals import parse_agent_json


class MainTests(unittest.TestCase):
    def test_normalize_issue_url_leaves_plain_url(self):
        value = "https://github.com/CodeBoarding/CodeBoarding/issues/343"
        self.assertEqual(normalize_issue_url(value), value)

    def test_normalize_issue_url_strips_issue_url_prefix(self):
        value = "issue_url=https://github.com/CodeBoarding/CodeBoarding/issues/343"
        expected = "https://github.com/CodeBoarding/CodeBoarding/issues/343"
        self.assertEqual(normalize_issue_url(value), expected)

    def test_normalize_issue_url_strips_url_prefix(self):
        value = "url=https://github.com/CodeBoarding/CodeBoarding/issues/343"
        expected = "https://github.com/CodeBoarding/CodeBoarding/issues/343"
        self.assertEqual(normalize_issue_url(value), expected)

    def test_normalize_issue_url_does_not_strip_unknown_key(self):
        value = "something=https://github.com/CodeBoarding/CodeBoarding/issues/343"
        self.assertEqual(normalize_issue_url(value), value)

    def test_parser_accepts_issue_url_flag(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "--issue-url",
                "https://github.com/CodeBoarding/CodeBoarding/issues/343",
                "--no-comments",
            ]
        )
        self.assertEqual(args.issue_url_opt, "https://github.com/CodeBoarding/CodeBoarding/issues/343")
        self.assertTrue(args.no_comments)

    def test_parse_agent_json_accepts_fenced_json(self):
        response = """```json
{"proceed": true, "classification": "bug", "signals": {"error_messages": ["boom"]}}
```"""
        self.assertEqual(parse_agent_json(response)["signals"]["error_messages"], ["boom"])

    def test_main_discards_agent_classified_feature_without_clone(self):
        issue = self._issue(
            comments=[
                {
                    "body": "This is not a bug. It should be tracked as an enhancement request.",
                    "user": {"login": "maintainer"},
                }
            ]
        )
        analysis = {
            "proceed": False,
            "classification": "enhancement",
            "discard_reason": "Maintainer classified it as an enhancement request.",
            "summary": "Request should be handled as enhancement, not bug.",
            "signals": {},
        }

        with patch("pr_factory.cli.main.GitHubClient") as client_cls, patch(
            "pr_factory.cli.main.analyze_issue_signals", return_value=analysis
        ), patch(
            "pr_factory.cli.main.clone_or_update_repository", side_effect=AssertionError("should not clone")
        ):
            client_cls.return_value.get_issue_from_url.return_value = issue
            code, output, error = self._run_main(["https://github.com/acme/widgets/issues/7"])

        self.assertEqual(code, 0, error)
        self.assertIn("Proceed: False", output)
        self.assertIn("Classification: enhancement", output)
        self.assertIn("Skipping repository clone.", output)

    def test_main_clones_after_genuine_bug_signal_analysis(self):
        issue = self._issue()
        analysis = {
            "proceed": True,
            "classification": "bug",
            "discard_reason": None,
            "summary": "Save crashes with TypeError.",
            "signals": {
                "error_messages": ["TypeError: cannot read property token"],
                "file_paths": ["src/auth.ts"],
                "symbols": ["AuthProvider"],
                "reproduction_steps": ["Open app", "Click save"],
                "keywords": ["auth", "token"],
            },
        }

        with tempfile.TemporaryDirectory(prefix="main-test-") as tmp, patch(
            "pr_factory.cli.main.GitHubClient"
        ) as client_cls, patch("pr_factory.cli.main.analyze_issue_signals", return_value=analysis), patch(
            "pr_factory.cli.main.clone_or_update_repository",
            return_value=(SimpleNamespace(path=Path(tmp) / ".projects" / "acme" / "widgets"), "cloned"),
        ), patch(
            "pr_factory.cli.main.get_or_detect_project_stack",
            return_value=SimpleNamespace(
                languages=["TypeScript"],
                frameworks=["React"],
                package_managers=["npm"],
                dependency_files=["package.json"],
                source_dirs=["src"],
                test_dirs=["tests"],
                config_files=[],
                test_commands=["npm run test"],
            ),
        ), patch(
            "pr_factory.cli.main.investigate_repository",
            return_value=SimpleNamespace(
                stack=SimpleNamespace(
                    languages=["TypeScript"],
                    frameworks=["React"],
                    package_managers=["npm"],
                    dependency_files=["package.json"],
                    source_dirs=["src"],
                    test_dirs=["tests"],
                    config_files=[],
                    test_commands=["npm run test"],
                ),
                search_terms=["AuthProvider", "token"],
                candidate_files=[],
                relevant_tests=["tests/auth.test.ts"],
            ),
        ), patch(
            "pr_factory.cli.main.prepare_issue_branch",
            return_value="pr-factory/issue-7-save-crashes",
        ), patch(
            "pr_factory.cli.main.retrieve_vector_context",
            return_value=[
                {
                    "path": "src/AuthProvider.tsx",
                    "content": "function AuthProvider() {}",
                    "semantic_score": 0.9,
                    "lexical_score": 1.0,
                    "combined_score": 0.94,
                    "start_line": 1,
                    "end_line": 3,
                }
            ],
        ), patch(
            "pr_factory.cli.main.run_planner_coder_workflow",
            return_value=SimpleNamespace(
                path=Path(tmp) / ".projects" / "acme" / "widgets" / ".pr-factory" / "tasks" / "issue-7.json",
                issue_number=7,
                planner_brief=object(),
                tasks=[SimpleNamespace(id="task-001", status="completed", title="Handle src/AuthProvider.tsx", error=None)],
                all_done=lambda: True,
                summary_counts=lambda: {"pending": 0, "running": 0, "completed": 1, "failed": 0},
            ),
        ), patch(
            "pr_factory.cli.main.run_qa",
            return_value=SimpleNamespace(
                passed=True,
                test_runs=[SimpleNamespace(command="pytest", returncode=0)],
                coverage_report="TOTAL 90%",
            ),
        ), patch(
            "pr_factory.cli.main.publish_fix",
            return_value=SimpleNamespace(
                changed_files=["src/AuthProvider.tsx"],
                branch="pr-factory/issue-7-save-crashes",
                commit_created=True,
                pushed=True,
                pull_request=SimpleNamespace(html_url="https://github.com/acme/widgets/pull/1"),
                skipped_reason=None,
            ),
        ):
            client_cls.return_value.get_issue_from_url.return_value = issue
            old_cwd = Path.cwd()
            os.chdir(tmp)
            try:
                code, output, error = self._run_main(["https://github.com/acme/widgets/issues/7"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0, error)
        self.assertIn("Proceed: True", output)
        self.assertIn("TypeError: cannot read property token", output)
        self.assertIn("Action: cloned", output)
        self.assertIn("Repository Investigation", output)
        self.assertIn("tests/auth.test.ts", output)
        self.assertIn("Qdrant Vector Context", output)
        self.assertIn("Planner/Coder Task Store", output)
        self.assertIn("task-001: completed", output)
        self.assertIn("QA / Coverage", output)
        self.assertIn("GitHub Pull Request", output)
        self.assertIn("https://github.com/acme/widgets/pull/1", output)

    @staticmethod
    def _run_main(args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def _issue(comments=None):
        return GitHubIssue(
            repository=RepositoryRef("acme", "widgets"),
            number=7,
            title="Save crashes",
            body="TypeError: cannot read property token when saving.",
            state="open",
            labels=["bug"],
            user="octocat",
            html_url="https://github.com/acme/widgets/issues/7",
            comments=comments or [],
        )


if __name__ == "__main__":
    unittest.main()
