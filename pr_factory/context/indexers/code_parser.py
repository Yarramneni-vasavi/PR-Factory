from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pr_factory.observability import get_logger

logger = get_logger(__name__)

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".cpp", ".c",
    ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".sh",
}
TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".css", ".html"}
ALL_EXTENSIONS = CODE_EXTENSIONS | TEXT_EXTENSIONS
SKIP_DIRS = {
    ".git", ".hg", ".svn", ".pr-factory", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build",
    "coverage", ".next", ".turbo", "target", "vendor",
}
MAX_FILE_BYTES = 512_000
CHUNK_SIZE = 80
CHUNK_OVERLAP = 15

SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
    re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b"),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>"),
    re.compile(r"^\s*(?:export\s+)?class\s+(?P<name>[A-Za-z_$][A-Za-z0-9_$]*)\b"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("),
]


@dataclass(frozen=True)
class ParsedChunk:
    name: str
    type: str
    content: str
    source: str
    start_line: int
    end_line: int


def parse_file(filepath: str | Path) -> list[ParsedChunk]:
    path = Path(filepath)
    if path.suffix.lower() not in ALL_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File too large to index: {path}")

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return []
    if path.suffix.lower() in CODE_EXTENSIONS:
        chunks = _symbol_chunks(lines, path)
        if chunks:
            return chunks
    return _sliding_window(lines, path)


def get_source_files(repo_path: str | Path, skip_dirs: Iterable[str] | None = None) -> list[str]:
    repo = Path(repo_path)
    skip = SKIP_DIRS | set(skip_dirs or [])
    files: list[str] = []
    for path in repo.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in ALL_EXTENSIONS:
            continue
        try:
            parts = path.relative_to(repo).parts
        except ValueError:
            continue
        if any(part in skip for part in parts):
            continue
        files.append(str(path))
    logger.info("Found %s source files in %s", len(files), repo)
    return sorted(files)


def _symbol_chunks(lines: list[str], path: Path) -> list[ParsedChunk]:
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        for pattern in SYMBOL_PATTERNS:
            match = pattern.match(line)
            if match:
                starts.append((index, match.group("name")))
                break
    chunks: list[ParsedChunk] = []
    for pos, (start, name) in enumerate(starts):
        end = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append(
                ParsedChunk(
                    name=name,
                    type="symbol",
                    content=content,
                    source=str(path),
                    start_line=start + 1,
                    end_line=end,
                )
            )
    return chunks


def _sliding_window(lines: list[str], path: Path) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
    for chunk_index, start in enumerate(range(0, len(lines), step)):
        end = min(start + CHUNK_SIZE, len(lines))
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append(
                ParsedChunk(
                    name=f"chunk_{chunk_index}",
                    type="block",
                    content=content,
                    source=str(path),
                    start_line=start + 1,
                    end_line=end,
                )
            )
        if end == len(lines):
            break
    return chunks
