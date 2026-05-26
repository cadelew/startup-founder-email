"""Job management API routes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

from startup_founder_email.api.job_store import JobStore
from startup_founder_email.api.schemas import CollectJobRequest
from startup_founder_email.api.worker import start_collect_job, start_pipeline_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def build_jobs_router(project_root: Path) -> APIRouter:
    """Create job routes bound to one project root."""

    job_store = JobStore(project_root / "data" / "jobs")

    @router.post("/collect")
    def create_collect_job(request_body: CollectJobRequest) -> dict[str, object]:
        seed_urls = tuple(
            seed_url.strip() for seed_url in request_body.seed_urls if seed_url.strip()
        )
        if not seed_urls:
            raise HTTPException(status_code=400, detail="At least one seed URL is required.")

        collection_mode = request_body.collection_mode.strip().lower()
        if collection_mode not in {"crawl", "scrape"}:
            raise HTTPException(
                status_code=400,
                detail="collection_mode must be 'crawl' or 'scrape'.",
            )

        job_record = job_store.create_job(
            seed_urls=list(seed_urls),
            collection_mode=collection_mode,
            scrape_json_extract=request_body.scrape_json_extract,
        )
        start_collect_job(
            project_root=project_root,
            job_store=job_store,
            job_id=job_record.job_id,
            seed_urls=seed_urls,
            collection_mode=collection_mode,
            scrape_json_extract=request_body.scrape_json_extract,
        )
        return asdict(job_record)

    @router.get("/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        job_record = job_store.get_job(job_id)
        if job_record is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return asdict(job_record)

    @router.post("/{job_id}/pipeline")
    def run_pipeline(job_id: str) -> dict[str, object]:
        job_record = job_store.get_job(job_id)
        if job_record is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job_record.status not in {"collect_completed", "done"}:
            raise HTTPException(
                status_code=409,
                detail="Collect must complete before running the pipeline.",
            )

        start_pipeline_job(
            project_root=project_root,
            job_store=job_store,
            job_id=job_id,
        )
        updated_job = job_store.get_job(job_id)
        if updated_job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        return asdict(updated_job)

    return router
