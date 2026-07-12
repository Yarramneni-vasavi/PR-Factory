from __future__ import annotations

from pathlib import Path

DEFAULT_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
MAX_SKILL_CHARS = 24_000


def load_planner_skills(skills_dir: str | Path | None = None) -> str:
    """Load planner guidance from package-local skill files."""

    root = Path(skills_dir) if skills_dir is not None else DEFAULT_SKILLS_DIR
    if not root.exists():
        return ""

    sections: list[str] = []
    total_chars = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue

        rel = path.relative_to(root).as_posix()
        section = f"## Skill: {rel}\n\n{content}"
        remaining = MAX_SKILL_CHARS - total_chars
        if remaining <= 0:
            break
        if len(section) > remaining:
            section = section[:remaining].rstrip() + "\n...[truncated]"
        sections.append(section)
        total_chars += len(section)

    return "\n\n".join(sections)
