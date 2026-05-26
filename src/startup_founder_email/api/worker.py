"""Background workers for API-driven pipeline jobs."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path

from startup_founder_email.api.job_store import JobStore
from startup_founder_email.cli import determine_stage_runner
from startup_founder_email.job_config import build_job_pipeline_config
from startup_founder_email.jsonl_io import iter_jsonl_records
from startup_founder_email.pipeline import build_pipeline_context_from_config

logger = logging.getLogger(__name__)

_PIPELINE_STAGE_NAMES = ("normalize", "enrich", "generate", "validate", "export")


def start_collect_job(
    *,
    project_root: Path,
    job_store: JobStore,
    job_id: str,
    seed_urls: tuple[str, ...],
    collection_mode: str,
    scrape_json_extract: bool = False,
) -> None:
    """Start collect work on a background thread."""

    worker_thread = threading.Thread(
        target=_run_collect_job,
        args=(project_root, job_store, job_id, seed_urls, collection_mode, scrape_json_extract),
        daemon=True,
    )
    worker_thread.start()


def start_pipeline_job(
    *,
    project_root: Path,
    job_store: JobStore,
    job_id: str,
) -> None:
    """Start downstream pipeline stages on a background thread."""

    worker_thread = threading.Thread(
        target=_run_pipeline_job,
        args=(project_root, job_store, job_id),
        daemon=True,
    )
    worker_thread.start()


def _run_collect_job(
    project_root: Path,
    job_store: JobStore,
    job_id: str,
    seed_urls: tuple[str, ...],
    collection_mode: str,
    scrape_json_extract: bool,
) -> None:
    job_record = job_store.get_job(job_id)
    if job_record is None:
        return

    job_record = replace(job_record, status="crawling")
    job_store.save_job(job_record)

    try:
        pipeline_config = build_job_pipeline_config(
            project_root,
            job_id=job_id,
            seed_urls=seed_urls,
            collection_mode=collection_mode,
            firecrawl_mode="live",
            scrape_json_extract=scrape_json_extract,
        )
        pipeline_context = build_pipeline_context_from_config(
            project_root,
            pipeline_config,
        )
        exit_code = determine_stage_runner("collect")(pipeline_context)
        if exit_code != 0:
            raise RuntimeError("Collect stage returned a non-zero exit code.")

        raw_path = pipeline_config.output_directories.raw_directory / "items.jsonl"
        page_count = sum(1 for _ in iter_jsonl_records(raw_path)) if raw_path.is_file() else 0
        job_record = replace(
            job_store.get_job(job_id) or job_record,
            status="collect_completed",
            page_count=page_count,
            error_message=None,
        )
        job_store.save_job(job_record)
    except Exception as error:  # noqa: BLE001 - surface job failures to API clients
        logger.exception("Collect job %s failed", job_id)
        job_record = replace(
            job_store.get_job(job_id) or job_record,
            status="error",
            error_message=str(error),
        )
        job_store.save_job(job_record)


def _run_pipeline_job(
    project_root: Path,
    job_store: JobStore,
    job_id: str,
) -> None:
    job_record = job_store.get_job(job_id)
    if job_record is None:
        return

    job_record = replace(job_record, status="processing")
    job_store.save_job(job_record)

    try:
        pipeline_context = build_pipeline_context_from_config(
            project_root,
            build_job_pipeline_config(
                project_root,
                job_id=job_id,
                seed_urls=tuple(job_record.seed_urls),
                collection_mode=job_record.collection_mode,
                firecrawl_mode="live",
                scrape_json_extract=job_record.scrape_json_extract,
            ),
        )
        completed_stages: list[str] = []
        for stage_name in _PIPELINE_STAGE_NAMES:
            exit_code = determine_stage_runner(stage_name)(pipeline_context)
            if exit_code != 0:
                raise RuntimeError(f"Stage {stage_name} returned a non-zero exit code.")
            completed_stages.append(stage_name)
            job_record = replace(
                job_store.get_job(job_id) or job_record,
                stages_completed=completed_stages,
            )
            job_store.save_job(job_record)

        job_record = replace(
            job_store.get_job(job_id) or job_record,
            status="done",
            error_message=None,
        )
        job_store.save_job(job_record)
    except Exception as error:  # noqa: BLE001 - surface job failures to API clients
        logger.exception("Pipeline job %s failed", job_id)
        job_record = replace(
            job_store.get_job(job_id) or job_record,
            status="error",
            error_message=str(error),
        )
        job_store.save_job(job_record)
