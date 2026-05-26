"""Persist background job state as JSON files."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class JobRecord:
    """One pipeline job tracked by the API."""

    job_id: str
    status: str
    seed_urls: list[str]
    collection_mode: str
    created_at_iso: str
    updated_at_iso: str
    scrape_json_extract: bool = False
    page_count: int = 0
    error_message: str | None = None
    stages_completed: list[str] = field(default_factory=list)


class JobStore:
    """Read and write job records under ``data/jobs``."""

    def __init__(self, jobs_directory: Path) -> None:
        self.jobs_directory = jobs_directory
        self.jobs_directory.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        *,
        seed_urls: list[str],
        collection_mode: str,
        scrape_json_extract: bool = False,
    ) -> JobRecord:
        """Create a queued job record."""

        timestamp = current_utc_timestamp()
        job_record = JobRecord(
            job_id=str(uuid.uuid4()),
            status="queued",
            seed_urls=seed_urls,
            collection_mode=collection_mode,
            scrape_json_extract=scrape_json_extract,
            created_at_iso=timestamp,
            updated_at_iso=timestamp,
        )
        self.save_job(job_record)
        return job_record

    def get_job(self, job_id: str) -> JobRecord | None:
        """Load one job record."""

        job_path = self.jobs_directory / f"{job_id}.json"
        if not job_path.is_file():
            return None
        with job_path.open(encoding="utf-8") as job_file:
            payload = json.load(job_file)
        return job_record_from_dict(payload)

    def save_job(self, job_record: JobRecord) -> None:
        """Persist one job record."""

        job_path = self.jobs_directory / f"{job_record.job_id}.json"
        job_record.updated_at_iso = current_utc_timestamp()
        with job_path.open("w", encoding="utf-8") as job_file:
            json.dump(asdict(job_record), job_file, indent=2, sort_keys=True)


def job_record_from_dict(payload: dict[str, Any]) -> JobRecord:
    """Convert stored JSON into a job record."""

    return JobRecord(
        job_id=str(payload["job_id"]),
        status=str(payload["status"]),
        seed_urls=[str(seed_url) for seed_url in payload.get("seed_urls", [])],
        collection_mode=str(payload.get("collection_mode", "crawl")),
        scrape_json_extract=bool(payload.get("scrape_json_extract", False)),
        created_at_iso=str(payload.get("created_at_iso", "")),
        updated_at_iso=str(payload.get("updated_at_iso", "")),
        page_count=int(payload.get("page_count", 0)),
        error_message=payload.get("error_message"),
        stages_completed=[
            str(stage_name) for stage_name in payload.get("stages_completed", [])
        ],
    )


def current_utc_timestamp() -> str:
    """Return a compact UTC timestamp."""

    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
