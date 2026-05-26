"""Pydantic models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CollectJobRequest(BaseModel):
    """Request body for starting a collect job."""

    seed_urls: list[str] = Field(min_length=1)
    collection_mode: str = "crawl"
    scrape_json_extract: bool = False


class ContactPatchRequest(BaseModel):
    """Manual overrides for one exported contact row."""

    best_email_guess: str | None = None
    public_email_address: str | None = None
    notes: str | None = None
    status: str | None = None
