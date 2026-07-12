from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


STACK_CACHE_PATH = Path(".pr-factory") / "project_stack.json"
MAX_FILE_BYTES = 512_000
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".pr-factory",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
    "target",
    "vendor",
}
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
TEST_MARKERS = (
    "/test/",
    "/tests/",
    "/__tests__/",
    "/spec/",
    "/specs/",
    ".test.",
    ".spec.",
    "_test.",
    "test_",
)


@dataclass(frozen=True)
class ProjectStack:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)
    source_dirs: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    term: str
    preview: str


@dataclass(frozen=True)
class CandidateFile:
    path: str
    score: int
    reasons: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)


@dataclass(frozen=True)
class RepositoryInvestigation:
    stack: ProjectStack
    search_terms: list[str]
    candidate_files: list[CandidateFile]
    relevant_tests: list[str]


def get_or_detect_project_stack(repo_path: str | Path, *, refresh: bool = False) -> ProjectStack:
    repo = Path(repo_path)
    cache = repo / STACK_CACHE_PATH
    if cache.exists() and not refresh:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return ProjectStack(**{key: data.get(key, []) for key in ProjectStack.__dataclass_fields__})
        except (OSError, TypeError, json.JSONDecodeError):
            pass

    stack = detect_project_stack(repo)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(asdict(stack), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return stack


def detect_project_stack(repo_path: str | Path) -> ProjectStack:
    repo = Path(repo_path)
    files = list(iter_repo_files(repo))
    rels = [normalize_path(path.relative_to(repo)) for path in files]
    rel_set = set(rels)

    languages = set()
    frameworks = set()
    package_managers = set()
    dependency_files = []
    config_files = []
    test_commands = set()

    extension_languages = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
    }
    for path in files:
        language = extension_languages.get(path.suffix.lower())
        if language:
            languages.add(language)

    def add_dep(name: str) -> None:
        if name in rel_set and name not in dependency_files:
            dependency_files.append(name)

    for name in (
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "package-lock.json",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "poetry.lock",
        "uv.lock",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "Gemfile",
    ):
        add_dep(name)

    for name in (
        "tsconfig.json",
        "vite.config.ts",
        "vite.config.js",
        "next.config.js",
        "next.config.mjs",
        "pytest.ini",
        "tox.ini",
        "ruff.toml",
        ".eslintrc.json",
        "eslint.config.js",
    ):
        if name in rel_set:
            config_files.append(name)

    package_json = repo / "package.json"
    if package_json.exists():
        package_managers.add(_detect_node_package_manager(rel_set))
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pkg = {}
        deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            if isinstance(pkg.get(key), dict):
                deps.update(pkg[key])
        dep_names = set(deps)
        for name, framework in (
            ("next", "Next.js"),
            ("react", "React"),
            ("vue", "Vue"),
            ("svelte", "Svelte"),
            ("express", "Express"),
            ("nestjs", "NestJS"),
            ("@nestjs/core", "NestJS"),
            ("vite", "Vite"),
        ):
            if name in dep_names:
                frameworks.add(framework)
        scripts = pkg.get("scripts") if isinstance(pkg, dict) else None
        if isinstance(scripts, dict):
            for script_name in ("test", "test:unit", "test:ci", "unit", "spec"):
                if script_name in scripts:
                    test_commands.add(f"{_package_runner(package_managers)} {script_name}")

    if "pyproject.toml" in rel_set or "requirements.txt" in rel_set:
        package_managers.add("pip")
        pyproject = _read_text(repo / "pyproject.toml")
        requirements = _read_text(repo / "requirements.txt")
        combined = f"{pyproject}\n{requirements}".lower()
        if "django" in combined:
            frameworks.add("Django")
        if "fastapi" in combined:
            frameworks.add("FastAPI")
        if "flask" in combined:
            frameworks.add("Flask")
        if "pytest" in combined or "pytest.ini" in rel_set:
            test_commands.add("python -m pytest")
        elif any(path.endswith("test.py") or "/test_" in path for path in rels):
            test_commands.add("python -m unittest discover")

    if "go.mod" in rel_set:
        package_managers.add("go")
        test_commands.add("go test ./...")
    if "Cargo.toml" in rel_set:
        package_managers.add("cargo")
        test_commands.add("cargo test")

    source_dirs = _top_level_dirs(rels, include_tests=False)
    test_dirs = _test_dirs(rels)

    return ProjectStack(
        languages=sorted(languages),
        frameworks=sorted(frameworks),
        package_managers=sorted(package_managers),
        dependency_files=dependency_files,
        source_dirs=source_dirs,
        test_dirs=test_dirs,
        config_files=sorted(config_files),
        test_commands=sorted(test_commands),
    )


def investigate_repository(repo_path: str | Path, signal_analysis: dict[str, Any], stack: ProjectStack) -> RepositoryInvestigation:
    repo = Path(repo_path)
    terms = extract_search_terms(signal_analysis)
    candidates = deterministic_search(repo, terms)
    tests = find_relevant_tests(repo, candidates, terms)
    return RepositoryInvestigation(
        stack=stack,
        search_terms=terms,
        candidate_files=candidates,
        relevant_tests=tests,
    )


def extract_search_terms(signal_analysis: dict[str, Any]) -> list[str]:
    signals = signal_analysis.get("signals") or {}
    raw_terms: list[str] = []
    for key in (
        "error_messages",
        "stack_traces",
        "file_paths",
        "symbols",
        "routes_or_endpoints",
        "commands",
        "test_names",
        "keywords",
    ):
        values = signals.get(key) or []
        if isinstance(values, str):
            values = [values]
        raw_terms.extend(str(value) for value in values if str(value).strip())

    for key in ("expected_behavior", "actual_behavior"):
        value = signals.get(key)
        if value:
            raw_terms.extend(_keyword_terms(str(value)))

    terms: list[str] = []
    seen = set()
    for term in raw_terms:
        for split_term in _expand_term(term):
            normalized = split_term.strip().strip("`'\"")
            if len(normalized) < 3:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(normalized)
    return terms[:80]


def deterministic_search(repo_path: str | Path, terms: list[str], *, max_candidates: int = 20) -> list[CandidateFile]:
    repo = Path(repo_path)
    by_path: dict[str, dict[str, Any]] = {}
    lower_terms = [(term, term.lower()) for term in terms]

    for file_path in iter_repo_files(repo):
        rel = normalize_path(file_path.relative_to(repo))
        rel_lower = rel.lower()
        is_test = is_test_path(rel)
        path_terms = [term for term, lower in lower_terms if lower in rel_lower]
        if path_terms:
            entry = by_path.setdefault(rel, {"score": 0, "reasons": [], "terms": set(), "hits": []})
            entry["score"] += 8 * len(path_terms)
            entry["reasons"].append("path matched issue signal")
            entry["terms"].update(path_terms)

        if is_test or not is_text_file(file_path):
            continue

        text = _read_text(file_path)
        if not text:
            continue
        text_lower = text.lower()
        matched_terms = [term for term, lower in lower_terms if lower in text_lower]
        if not matched_terms:
            continue

        entry = by_path.setdefault(rel, {"score": 0, "reasons": [], "terms": set(), "hits": []})
        entry["score"] += len(matched_terms)
        entry["reasons"].append("content matched issue signal")
        entry["terms"].update(matched_terms)
        entry["hits"].extend(_line_hits(rel, text, matched_terms, limit=8))

    candidates = [
        CandidateFile(
            path=path,
            score=int(data["score"]),
            reasons=sorted(set(data["reasons"])),
            matched_terms=sorted(data["terms"], key=str.lower),
            hits=data["hits"][:8],
        )
        for path, data in by_path.items()
        if not is_test_path(path)
    ]
    candidates.sort(key=lambda item: (-item.score, item.path))
    return candidates[:max_candidates]


def find_relevant_tests(repo_path: str | Path, candidates: list[CandidateFile], terms: list[str], *, max_tests: int = 20) -> list[str]:
    repo = Path(repo_path)
    test_files = [path for path in iter_repo_files(repo) if is_test_path(normalize_path(path.relative_to(repo)))]
    if not test_files:
        return []

    candidate_paths = [candidate.path for candidate in candidates]
    candidate_stems = {Path(path).stem.lower().replace(".test", "").replace(".spec", "") for path in candidate_paths}
    lower_terms = [term.lower() for term in terms]
    scored: list[tuple[int, str]] = []

    for test_path in test_files:
        rel = normalize_path(test_path.relative_to(repo))
        rel_lower = rel.lower()
        score = 0
        for stem in candidate_stems:
            if stem and stem in rel_lower:
                score += 10
        for candidate in candidate_paths:
            if _same_feature_path(candidate, rel):
                score += 6
        text = _read_text(test_path) if is_text_file(test_path) else ""
        text_lower = text.lower()
        term_hits = sum(1 for term in lower_terms if term and (term in rel_lower or term in text_lower))
        score += term_hits
        if score:
            scored.append((score, rel))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in scored[:max_tests]]


def iter_repo_files(repo_path: str | Path) -> Iterable[Path]:
    repo = Path(repo_path)
    for path in repo.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(repo).parts
        except ValueError:
            continue
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        yield path


def is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if path.name in {"Dockerfile", "Makefile", "Rakefile", "Gemfile", "Procfile"}:
        return True
    return False


def is_test_path(path: str) -> bool:
    normalized = f"/{path.lower()}"
    return any(marker in normalized for marker in TEST_MARKERS)


def normalize_path(path: Path) -> str:
    return path.as_posix()


def _detect_node_package_manager(rel_set: set[str]) -> str:
    if "pnpm-lock.yaml" in rel_set:
        return "pnpm"
    if "yarn.lock" in rel_set:
        return "yarn"
    if "package-lock.json" in rel_set:
        return "npm"
    return "npm"


def _package_runner(package_managers: set[str]) -> str:
    if "pnpm" in package_managers:
        return "pnpm"
    if "yarn" in package_managers:
        return "yarn"
    return "npm run"


def _top_level_dirs(rels: list[str], *, include_tests: bool) -> list[str]:
    dirs = set()
    for rel in rels:
        parts = rel.split("/")
        if len(parts) < 2:
            continue
        first = parts[0]
        if first in EXCLUDED_DIRS:
            continue
        if not include_tests and is_test_path(rel):
            continue
        if first in {"src", "app", "lib", "packages", "server", "client", "web", "api", "cmd", "pkg"}:
            dirs.add(first)
    return sorted(dirs)


def _test_dirs(rels: list[str]) -> list[str]:
    dirs = set()
    for rel in rels:
        if not is_test_path(rel):
            continue
        parts = rel.split("/")
        if len(parts) > 1:
            dirs.add(parts[0] if parts[0] != "src" else "/".join(parts[:2]))
    return sorted(dirs)


def _read_text(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _expand_term(term: str) -> list[str]:
    expanded = [term]
    expanded.extend(re.findall(r"[A-Za-z_][A-Za-z0-9_.$:-]{2,}", term))
    expanded.extend(re.findall(r"[\w./-]+\.(?:py|js|jsx|ts|tsx|go|rs|java|rb|php|cs)", term))
    return expanded


def _keyword_terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "that", "this", "when", "then", "from", "should", "actual", "expected"}
    return [word for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", text) if word.lower() not in stop]


def _line_hits(rel: str, text: str, terms: list[str], *, limit: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    lower_terms = [(term, term.lower()) for term in terms]
    for line_number, line in enumerate(text.splitlines(), start=1):
        lower_line = line.lower()
        for term, lower in lower_terms:
            if lower in lower_line:
                hits.append(SearchHit(path=rel, line=line_number, term=term, preview=line.strip()[:180]))
                break
        if len(hits) >= limit:
            break
    return hits


def _same_feature_path(source_path: str, test_path: str) -> bool:
    source_parts = [part for part in Path(source_path).parts if part not in {"src", "lib", "app"}]
    test_parts = [part for part in Path(test_path).parts if part not in {"tests", "test", "__tests__", "src", "lib", "app"}]
    if not source_parts or not test_parts:
        return False
    return bool(set(part.lower() for part in source_parts[:-1]) & set(part.lower() for part in test_parts[:-1]))
