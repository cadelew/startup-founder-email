from pathlib import Path

from startup_founder_email.api.contacts_service import (
    build_job_exported_directory,
    patch_contact,
    read_contacts,
)


def test_read_contacts_uses_job_scoped_export(tmp_path: Path) -> None:
    exported_directory = build_job_exported_directory(tmp_path, "job-123")
    exported_directory.mkdir(parents=True)
    (exported_directory / "contacts.csv").write_text(
        "founder_full_name,company_name,best_email_guess\n"
        "Ada Lovelace,Example,ada@example.com\n",
        encoding="utf-8",
    )

    contacts = read_contacts(tmp_path, "job-123")

    assert contacts["total"] == 1
    assert contacts["csv_path"] == str(exported_directory / "contacts.csv")
    assert contacts["items"][0]["best_email_guess"] == "ada@example.com"


def test_patch_contact_writes_job_scoped_overrides(tmp_path: Path) -> None:
    exported_directory = build_job_exported_directory(tmp_path, "job-123")
    exported_directory.mkdir(parents=True)
    (exported_directory / "contacts.csv").write_text(
        "founder_full_name,company_name,best_email_guess\n"
        "Ada Lovelace,Example,ada@example.com\n",
        encoding="utf-8",
    )
    row_id = read_contacts(tmp_path, "job-123")["items"][0]["row_id"]

    updated_row = patch_contact(
        tmp_path,
        "job-123",
        row_id,
        {"best_email_guess": "ada.lovelace@example.com"},
    )

    assert updated_row is not None
    assert updated_row["best_email_guess"] == "ada.lovelace@example.com"
    assert (exported_directory / "contact_overrides.json").is_file()
