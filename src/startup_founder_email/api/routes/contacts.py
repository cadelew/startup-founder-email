"""Contact review API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from startup_founder_email.api.contacts_service import (
    build_job_exported_directory,
    patch_contact,
    read_contacts,
)
from startup_founder_email.api.schemas import ContactPatchRequest

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


def build_contacts_router(project_root: Path) -> APIRouter:
    """Create contact routes bound to one project root."""

    @router.get("")
    def list_contacts(
        job_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        return read_contacts(project_root, job_id, limit=limit, offset=offset)

    @router.patch("/{row_id}")
    def update_contact(
        row_id: str,
        request_body: ContactPatchRequest,
        job_id: str,
    ) -> dict[str, object]:
        updated_row = patch_contact(
            project_root,
            job_id,
            row_id,
            request_body.model_dump(exclude_none=True),
        )
        if updated_row is None:
            raise HTTPException(status_code=404, detail="Contact row not found.")
        return updated_row

    @router.get("/export.csv")
    def download_contacts_csv(job_id: str) -> FileResponse:
        exported_directory = build_job_exported_directory(project_root, job_id)
        contacts_csv_path = exported_directory / "contacts.csv"
        if not contacts_csv_path.is_file():
            raise HTTPException(status_code=404, detail="Exported contacts.csv not found.")
        return FileResponse(
            path=contacts_csv_path,
            media_type="text/csv",
            filename="contacts.csv",
        )

    return router
