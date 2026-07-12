import json
import tempfile
import unittest
from pathlib import Path

from pr_factory.repo_investigation import (
    detect_project_stack,
    extract_search_terms,
    get_or_detect_project_stack,
    investigate_repository,
)


class RepoInvestigationTests(unittest.TestCase):
    def test_detect_project_stack_caches_node_typescript_project(self):
        with tempfile.TemporaryDirectory(prefix="repo-stack-test-") as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            (repo / "package.json").write_text(
                json.dumps(
                    {
                        "scripts": {"test": "vitest run"},
                        "dependencies": {"react": "latest"},
                        "devDependencies": {"vite": "latest", "typescript": "latest"},
                    }
                ),
                encoding="utf-8",
            )
            (repo / "package-lock.json").write_text("{}", encoding="utf-8")
            (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
            (repo / "src" / "AuthProvider.tsx").write_text("export function AuthProvider() {}\n", encoding="utf-8")
            (repo / "tests" / "AuthProvider.test.tsx").write_text("test('auth', () => {})\n", encoding="utf-8")

            stack = get_or_detect_project_stack(repo, refresh=True)

            self.assertIn("TypeScript", stack.languages)
            self.assertIn("React", stack.frameworks)
            self.assertIn("Vite", stack.frameworks)
            self.assertIn("npm", stack.package_managers)
            self.assertIn("package.json", stack.dependency_files)
            self.assertIn("src", stack.source_dirs)
            self.assertIn("tests", stack.test_dirs)
            self.assertIn("npm run test", stack.test_commands)
            self.assertTrue((repo / ".pr-factory" / "project_stack.json").exists())

    def test_deterministic_search_finds_candidate_files_and_relevant_tests(self):
        with tempfile.TemporaryDirectory(prefix="repo-search-test-") as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest"}, "dependencies": {"react": "latest"}}),
                encoding="utf-8",
            )
            (repo / "src" / "AuthProvider.tsx").write_text(
                "export function AuthProvider() {\n  throw new TypeError('cannot read property token');\n}\n",
                encoding="utf-8",
            )
            (repo / "src" / "Other.ts").write_text("export const other = 1;\n", encoding="utf-8")
            (repo / "tests" / "AuthProvider.test.tsx").write_text(
                "import { AuthProvider } from '../src/AuthProvider';\ntest('token refresh', () => {});\n",
                encoding="utf-8",
            )

            analysis = {
                "signals": {
                    "error_messages": ["TypeError: cannot read property token"],
                    "symbols": ["AuthProvider"],
                    "file_paths": ["src/AuthProvider.tsx"],
                    "keywords": ["token"],
                }
            }
            stack = detect_project_stack(repo)
            investigation = investigate_repository(repo, analysis, stack)

            self.assertIn("AuthProvider", investigation.search_terms)
            self.assertEqual(investigation.candidate_files[0].path, "src/AuthProvider.tsx")
            self.assertIn("tests/AuthProvider.test.tsx", investigation.relevant_tests)

    def test_extract_search_terms_deduplicates_and_expands_errors(self):
        analysis = {
            "signals": {
                "error_messages": ["TypeError: cannot read property token in AuthProvider"],
                "symbols": ["AuthProvider"],
                "keywords": ["token"],
            }
        }

        terms = extract_search_terms(analysis)

        self.assertIn("TypeError: cannot read property token in AuthProvider", terms)
        self.assertIn("AuthProvider", terms)
        self.assertIn("token", terms)
        self.assertEqual(len(terms), len({term.lower() for term in terms}))


if __name__ == "__main__":
    unittest.main()
