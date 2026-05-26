"""Tests for API job persistence."""

from __future__ import annotations

import json
from pathlib import Path

from startup_founder_email.api.job_store import JobStore


def test_create_job_persists_scrape_json_extract(tmp_path: Path) -> None:
    job_store = JobStore(tmp_path / "jobs")
    job_record = job_store.create_job(
        seed_urls=["https://terac.com/"],
        collection_mode="crawl",
        scrape_json_extract=True,
    )

    saved_payload = json.loads((tmp_path / "jobs" / f"{job_record.job_id}.json").read_text())
    assert saved_payload["scrape_json_extract"] is True

    reloaded = job_store.get_job(job_record.job_id)
    assert reloaded is not None
    assert reloaded.scrape_json_extract is True
