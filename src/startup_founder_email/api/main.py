"""FastAPI application for the founder outreach pipeline."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from startup_founder_email.api.routes.contacts import build_contacts_router
from startup_founder_email.api.routes.jobs import build_jobs_router
from startup_founder_email.config import load_pipeline_config


def create_app(project_root: Path | None = None) -> FastAPI:
    """Create the FastAPI app for one project root."""

    resolved_project_root = (
        project_root
        if project_root is not None
        else Path(os.environ.get("STARTUP_FOUNDER_EMAIL_PROJECT_ROOT", Path.cwd()))
    ).resolve()
    app = FastAPI(
        title="Startup Founder Email",
        description="Run collection and review founder outreach contacts.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(build_jobs_router(resolved_project_root))
    app.include_router(build_contacts_router(resolved_project_root))

    @app.get("/api/health")
    def health_check() -> dict[str, object]:
        pipeline_config = load_pipeline_config(resolved_project_root)
        firecrawl_ok = check_http_endpoint(
            f"{pipeline_config.firecrawl.base_url.rstrip('/')}/",
        )
        return {
            "status": "ok",
            "project_root": str(resolved_project_root),
            "firecrawl_reachable": firecrawl_ok,
        }

    return app


def check_http_endpoint(url: str, timeout_seconds: float = 3.0) -> bool:
    """Return whether an HTTP endpoint responds."""

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False


app = create_app()
