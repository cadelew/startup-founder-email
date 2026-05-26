"""Typed record models shared across pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawCompanyRecord:
    """A direct record captured from the source before cleanup."""

    source_name: str
    source_url: str
    fetched_at_iso: str
    raw_company_description: str | None
    payload: dict[str, Any]


@dataclass(frozen=True)
class FirecrawlPageRecord:
    """A page captured from Firecrawl or an offline Firecrawl-shaped fixture."""

    url: str
    fetched_at_iso: str
    status_code: int | None
    markdown: str | None
    html: str | None
    links: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    llm_extraction: dict[str, Any] | None = None
    seed_url: str | None = None
    crawl_id: str | None = None


@dataclass(frozen=True)
class NormalizedFounderRecord:
    """A cleaned founder/company row ready for enrichment."""

    company_name: str
    batch_name: str | None
    industry_name: str | None
    company_website_url: str | None
    raw_company_description: str | None
    founder_full_name: str
    founder_first_name: str | None
    founder_last_name: str | None
    founder_role_title: str | None
    founder_linkedin_url: str | None
    source_url: str
    seed_url: str | None = None
    public_email_address: str | None = None
    public_email_source_type: str = ""
    cleaning_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DomainEnrichmentRecord:
    """Metadata discovered from a company's website and DNS records."""

    company_name: str
    raw_company_description: str | None
    canonical_company_domain: str | None
    final_website_url: str | None
    has_mx_records: bool
    mx_provider_name: str | None
    enrichment_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ContactCandidateRecord:
    """A final outreach row containing public or inferred contact data."""

    founder_full_name: str
    company_name: str
    batch_name: str | None
    industry_name: str | None
    company_website_url: str | None
    raw_company_description: str | None
    company_summary: str | None
    canonical_company_domain: str | None
    public_email_address: str | None
    public_email_source_type: str
    best_email_guess: str | None
    alternative_email_guess: str | None
    email_source_type: str
    email_confidence_level: str
    mx_provider_name: str | None
    founder_linkedin_url: str | None
    source_url: str
    syntax_valid: bool = False
    is_role_address: bool = False
    is_disposable_domain: bool = False
    mx_provider_known: bool = False
    smtp_probe_status: str = "skipped"
    validation_notes: tuple[str, ...] = field(default_factory=tuple)
    status: str = ""
    notes: str = ""
