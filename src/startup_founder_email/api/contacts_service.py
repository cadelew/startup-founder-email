"""Read and update exported contacts for the API."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def build_contact_row_id(founder_full_name: str, company_name: str) -> str:
    """Build a stable row identifier for one exported contact."""

    raw_key = f"{founder_full_name.strip().lower()}|{company_name.strip().lower()}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def read_contacts(
    project_root: Path,
    job_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Read contacts from CSV and merge manual overrides."""

    exported_directory = build_job_exported_directory(project_root, job_id)
    contacts_csv_path = exported_directory / "contacts.csv"
    if not contacts_csv_path.is_file():
        return {"total": 0, "columns": [], "items": [], "csv_path": str(contacts_csv_path)}

    overrides = read_contact_overrides(exported_directory)
    with contacts_csv_path.open(encoding="utf-8", newline="") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        columns = list(csv_reader.fieldnames or [])
        rows = list(csv_reader)

    items: list[dict[str, Any]] = []
    for row in rows:
        row_id = build_contact_row_id(
            row.get("founder_full_name", ""),
            row.get("company_name", ""),
        )
        merged_row = dict(row)
        merged_row["row_id"] = row_id
        if row_id in overrides:
            merged_row.update(overrides[row_id])
        items.append(merged_row)

    total = len(items)
    paginated_items = items[offset : offset + limit]
    return {
        "total": total,
        "columns": columns,
        "items": paginated_items,
        "csv_path": str(contacts_csv_path),
    }


def patch_contact(
    project_root: Path,
    job_id: str,
    row_id: str,
    updates: dict[str, str],
) -> dict[str, Any] | None:
    """Apply manual field overrides for one contact row."""

    exported_directory = build_job_exported_directory(project_root, job_id)
    contacts = read_contacts(project_root, job_id, limit=10_000, offset=0)
    matching_rows = [
        contact_row
        for contact_row in contacts["items"]
        if contact_row.get("row_id") == row_id
    ]
    if not matching_rows:
        return None

    overrides = read_contact_overrides(exported_directory)
    allowed_fields = {
        "best_email_guess",
        "public_email_address",
        "notes",
        "status",
    }
    filtered_updates = {
        field_name: field_value
        for field_name, field_value in updates.items()
        if field_name in allowed_fields and field_value is not None
    }
    overrides[row_id] = {**overrides.get(row_id, {}), **filtered_updates}
    write_contact_overrides(exported_directory, overrides)

    merged_row = dict(matching_rows[0])
    merged_row.update(filtered_updates)
    return merged_row


def build_job_exported_directory(project_root: Path, job_id: str) -> Path:
    """Return the exported contacts directory for one API job."""

    return project_root / "data" / "jobs" / job_id / "exported"


def read_contact_overrides(exported_directory: Path) -> dict[str, dict[str, str]]:
    """Load manual contact overrides from disk."""

    overrides_path = exported_directory / "contact_overrides.json"
    if not overrides_path.is_file():
        return {}
    with overrides_path.open(encoding="utf-8") as overrides_file:
        payload = json.load(overrides_file)
    if not isinstance(payload, dict):
        return {}
    return {
        str(row_id): {
            str(field_name): str(field_value)
            for field_name, field_value in override_values.items()
            if isinstance(field_name, str) and isinstance(field_value, str)
        }
        for row_id, override_values in payload.items()
        if isinstance(override_values, dict)
    }


def write_contact_overrides(
    exported_directory: Path,
    overrides: dict[str, dict[str, str]],
) -> None:
    """Persist manual contact overrides."""

    exported_directory.mkdir(parents=True, exist_ok=True)
    overrides_path = exported_directory / "contact_overrides.json"
    with overrides_path.open("w", encoding="utf-8") as overrides_file:
        json.dump(overrides, overrides_file, indent=2, sort_keys=True)
