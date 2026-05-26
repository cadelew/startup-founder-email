"""Run the FastAPI development server."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn


def main() -> None:
    """Start uvicorn for the outreach API."""

    argument_parser = argparse.ArgumentParser(description="Run the outreach API server.")
    argument_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository root.",
    )
    argument_parser.add_argument("--host", default="127.0.0.1")
    argument_parser.add_argument("--port", type=int, default=8000)
    parsed_arguments = argument_parser.parse_args()
    project_root = parsed_arguments.project_root.resolve()
    os.environ["STARTUP_FOUNDER_EMAIL_PROJECT_ROOT"] = str(project_root)
    uvicorn.run(
        "startup_founder_email.api.main:app",
        host=parsed_arguments.host,
        port=parsed_arguments.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
