# Phase 4: VC portfolio discovery (deferred)

This document describes the planned **discover** stage. It is **not implemented yet**.
The current MVP uses **crawl-first** collection: you supply startup homepage URLs
(environment variable, seeds CSV, or the web UI) and the pipeline crawls each site.

## North-star flow

```text
VC portfolio page  →  discover stage  →  companies.jsonl
companies.jsonl    →  collect (crawl)  →  raw pages
raw pages          →  normalize … export → contacts.csv
```

## Planned `discover` stage

| Step | Output | Notes |
|------|--------|-------|
| Scrape/crawl VC portfolio URL | `data/discovered/companies.jsonl` | Rows use [`RawCompanyRecord`](../src/startup_founder_email/models.py) |
| Feed seeds into collect | `FirecrawlConfig.target_urls` | One homepage per company |

### YC (recommended first adapter)

- Source: `https://www.ycombinator.com/companies`
- Approach options:
  - Firecrawl crawl + JSON extraction for `{ name, website, batch }`
  - Dedicated HTML parser if the listing structure is stable
- Expect Cloudflare (see [`AntiBotTest.md`](../AntiBotTest.md))

### Other VCs (later adapters)

Each firm uses a different portfolio layout. Plan on **one adapter per source**
(Sequoia, First Round, etc.) rather than one generic scraper.

## Wiring after discover exists

```bash
# Future CLI shape (not implemented)
python -m startup_founder_email --project-root . discover
python -m startup_founder_email --project-root . collect   # reads discovered URLs
```

Environment variable sketch:

```bash
export STARTUP_FOUNDER_EMAIL_DISCOVER_SOURCES=yc
export STARTUP_FOUNDER_EMAIL_YC_COMPANIES_URL=https://www.ycombinator.com/companies
```

## Why this is deferred

1. **Crawl-first** validates per-startup extraction without portfolio complexity.
2. VC sites are **heterogeneous** and often **bot-protected**.
3. The web UI and job API are easier to test with a small hand-picked seed list.

Implement discover only after crawl + UI reliably produce clean `contacts.csv` rows.
