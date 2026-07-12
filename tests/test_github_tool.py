import os
import tempfile
import unittest
from pathlib import Path

from pr_factory.github_tool import GitRepository, RepositoryRef, parse_github_issue_url


class GitHubToolTests(unittest.TestCase):
    def test_parse_github_issue_url(self):
        repository, number = parse_github_issue_url("https://github.com/nous/pr-factory/issues/42")

        self.assertEqual(repository.owner, "nous")
        self.assertEqual(repository.repo, "pr-factory")
        self.assertEqual(repository.full_name, "nous/pr-factory")
        self.assertEqual(number, 42)

    def test_parse_github_issue_url_rejects_non_issue_url(self):
        with self.assertRaises(ValueError):
            parse_github_issue_url("https://github.com/nous/pr-factory/pull/42")

    def test_clone_branch_commit_and_push_to_bare_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            source = root / "source"
            clone = root / "clone"

            self._git(["init", "--bare", str(remote)], cwd=root)
            self._git(["init", str(source)], cwd=root)
            self._configure_user(source)
            (source / "README.md").write_text("hello\n", encoding="utf-8")
            self._git(["add", "README.md"], cwd=source)
            self._git(["commit", "-m", "initial"], cwd=source)
            self._git(["branch", "-M", "main"], cwd=source)
            self._git(["remote", "add", "origin", str(remote)], cwd=source)
            self._git(["push", "-u", "origin", "main"], cwd=source)

            repo = GitRepository.clone(str(remote), clone, branch="main")
            self._configure_user(clone)
            repo.checkout_new_branch("fix/example")
            (clone / "README.md").write_text("hello\nfixed\n", encoding="utf-8")
            repo.add("README.md")
            repo.commit("fix example")
            push_result = repo.push(branch="fix/example")

            self.assertTrue(push_result.ok)
            branch_check = self._git(
                ["show-ref", "--verify", "refs/heads/fix/example"],
                cwd=remote,
            )
            self.assertEqual(branch_check.returncode, 0)

    def test_rebase_conflict_detection_and_strategy_resolution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_path = root / "repo"

            repo_path.mkdir()
            self._git(["init"], cwd=repo_path)
            self._configure_user(repo_path)
            (repo_path / "file.txt").write_text("base\n", encoding="utf-8")
            self._git(["add", "file.txt"], cwd=repo_path)
            self._git(["commit", "-m", "base"], cwd=repo_path)
            self._git(["branch", "-M", "main"], cwd=repo_path)

            self._git(["checkout", "-b", "feature"], cwd=repo_path)
            (repo_path / "file.txt").write_text("feature\n", encoding="utf-8")
            self._git(["commit", "-am", "feature change"], cwd=repo_path)

            self._git(["checkout", "main"], cwd=repo_path)
            (repo_path / "file.txt").write_text("main\n", encoding="utf-8")
            self._git(["commit", "-am", "main change"], cwd=repo_path)

            self._git(["checkout", "feature"], cwd=repo_path)
            repo = GitRepository(repo_path)
            rebase = repo.rebase("main")

            self.assertFalse(rebase.ok)
            conflict_status = repo.conflict_status()
            self.assertTrue(conflict_status.has_conflicts)
            self.assertEqual(conflict_status.operation, "rebase")
            self.assertEqual(conflict_status.files, ["file.txt"])

            resolution = repo.resolve_conflict_with_strategy("file.txt", "theirs")
            self.assertTrue(resolution.ok)
            self.assertFalse(repo.conflict_status().has_conflicts)
            repo.abort_rebase()

    @staticmethod
    def _configure_user(repo_path: Path):
        GitHubToolTests._git(["config", "user.email", "test@example.com"], cwd=repo_path)
        GitHubToolTests._git(["config", "user.name", "Test User"], cwd=repo_path)

    @staticmethod
    def _git(args, cwd: Path):
        import subprocess

        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "Test User")
        env.setdefault("GIT_AUTHOR_EMAIL", "test@example.com")
        env.setdefault("GIT_COMMITTER_NAME", "Test User")
        env.setdefault("GIT_COMMITTER_EMAIL", "test@example.com")
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
