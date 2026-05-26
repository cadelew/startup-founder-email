from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import NormalizedFounderRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.enrich import (
    canonicalize_company_domain,
    classify_mx_provider,
    enrich_normalized_founder_record,
    lookup_mx_records,
    run_enrichment_stage,
)


def test_canonicalize_company_domain_strips_scheme_and_www() -> None:
    assert canonicalize_company_domain("https://www.Example.com/about") == "example.com"


def test_enrich_normalized_founder_record_records_mx_lookup(monkeypatch) -> None:
    normalized_founder_record = build_normalized_founder_record()
    monkeypatch.setattr(
        "startup_founder_email.stages.enrich.lookup_mx_records",
        lambda domain: (True, "google", "mx_lookup_ok"),
    )

    enrichment_record = enrich_normalized_founder_record(normalized_founder_record)

    assert enrichment_record.canonical_company_domain == "example.com"
    assert enrichment_record.has_mx_records is True
    assert enrichment_record.mx_provider_name == "google"
    assert enrichment_record.enrichment_notes == ("mx_lookup_ok",)


def test_lookup_mx_records_falls_back_when_dns_package_is_unavailable(monkeypatch) -> None:
    original_import = __import__

    def raise_import_error_for_dns(name, *args, **kwargs):
        if name == "dns.resolver":
            raise ImportError("dns is not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", raise_import_error_for_dns)

    assert lookup_mx_records("example.com") == (False, None, "mx_lookup_unavailable")


def test_classify_mx_provider_maps_common_hosts() -> None:
    assert classify_mx_provider("aspmx.l.google.com") == "google"
    assert classify_mx_provider("example-com.mail.protection.outlook.com") == "microsoft"
    assert classify_mx_provider("mx.unknown.example") == "mx.unknown.example"


def test_run_enrichment_stage_writes_enriched_jsonl(tmp_path, monkeypatch) -> None:
    context = build_pipeline_context(tmp_path)
    normalized_path = context.config.output_directories.normalized_directory / "items.jsonl"
    write_jsonl_records(normalized_path, [build_normalized_founder_record()])
    monkeypatch.setattr(
        "startup_founder_email.stages.enrich.lookup_mx_records",
        lambda domain: (False, None, "mx_not_found"),
    )

    exit_code = run_enrichment_stage(context)
    output_path = context.config.output_directories.enriched_directory / "items.jsonl"
    enrichment_records = list(iter_jsonl_records(output_path))

    assert exit_code == 0
    assert enrichment_records[0]["canonical_company_domain"] == "example.com"
    assert enrichment_records[0]["enrichment_notes"] == ["mx_not_found"]


def build_normalized_founder_record() -> NormalizedFounderRecord:
    return NormalizedFounderRecord(
        company_name="Example",
        batch_name=None,
        industry_name=None,
        company_website_url="https://www.Example.com/about",
        raw_company_description="Example builds tools.",
        founder_full_name="Ada Lovelace",
        founder_first_name="Ada",
        founder_last_name="Lovelace",
        founder_role_title="CTO",
        founder_linkedin_url=None,
        source_url="https://www.Example.com/about",
    )
