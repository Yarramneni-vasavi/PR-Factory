from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(dotenv_path: str | Path = ".env", *, override: bool = False) -> None:
    """Load key/value pairs from a .env file into the process environment.

    This is intentionally dependency-light (no python-dotenv) and supports the
    common subset needed for local development.
    """

    path = Path(dotenv_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        if override or key not in os.environ:
            os.environ[key] = value


def signal_agent_model() -> str:
    return os.getenv("PR_FACTORY_SIGNAL_AGENT_MODEL", "gpt-5-mini")

