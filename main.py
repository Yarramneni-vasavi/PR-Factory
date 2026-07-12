"""Convenience entrypoint for the PR Factory CLI.

Keep this file tiny so it is easy to swap the execution surface later
(e.g. FastAPI) while reusing the same core modules under pr_factory/.
"""

from __future__ import annotations

from pr_factory.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
