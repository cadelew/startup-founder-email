# startup-founder-email

A readable Python data pipeline for building a manual founder outreach list.

## Pipeline shape

This project is intentionally split into small stages:

1. `collect`
2. `normalize`
3. `enrich`
4. `generate`
5. `export`

That separation is the core idea behind most scraping and data-engineering projects.
Each stage takes an input artifact, transforms it, and writes a new output artifact.
This makes the pipeline easier to debug, rerun, and learn from.

## Current status

Implemented so far:

- project scaffolding
- CLI entrypoint
- typed data models
- config loading
- logging setup
- output directory management
- fixture-based collection
- optional live Firecrawl scraping through `/v1/scrape` (optional `formats: json` / LLM extraction when Firecrawl has AI configured)
- normalization, enrichment, generation, validation, and CSV export

Fixture mode is the default so the pipeline can run without network access.

## Quick start

```bash
python -m startup_founder_email --project-root . collect
python -m startup_founder_email --project-root . normalize
python -m startup_founder_email --project-root . enrich
python -m startup_founder_email --project-root . generate
python -m startup_founder_email --project-root . validate
python -m startup_founder_email --project-root . export
```

To collect live pages with a local Firecrawl server:

```bash
export STARTUP_FOUNDER_EMAIL_FIRECRAWL_MODE=live
export FIRECRAWL_BASE_URL=http://localhost:3002
export STARTUP_FOUNDER_EMAIL_FIRECRAWL_URLS=https://example.com,https://example.org
python -m startup_founder_email --project-root . collect
```

When Firecrawl is set up with Ollama or another LLM (see `firecrawl/.env`), you can enable adaptive structured founder extraction. The collector first scrapes markdown/HTML/links; if cheap signals indicate the deterministic parser may struggle (for example no founder signal or nav-heavy markdown), it makes a second scrape with Firecrawl JSON extraction. Raw JSON is stored on each record as `llm_extraction`, and `normalize` prefers those founders when the array is non-empty:

```bash
export STARTUP_FOUNDER_EMAIL_FIRECRAWL_JSON_EXTRACT=true
# Optional: override HTTP timeout (seconds) for slow local models
export STARTUP_FOUNDER_EMAIL_FIRECRAWL_LLM_TIMEOUT_SECONDS=180
python -m startup_founder_email --project-root . collect
```

To enable opt-in live email verification with Reacher HTTP backend during `validate`:

```bash
# In a separate terminal, run Reacher (requires outbound SMTP connectivity)
docker run --rm -p 8080:8080 reacherhq/backend:latest

# In your pipeline terminal:
export STARTUP_FOUNDER_EMAIL_REACHER_ENABLE=true
export STARTUP_FOUNDER_EMAIL_REACHER_BASE_URL=http://localhost:8080
export STARTUP_FOUNDER_EMAIL_REACHER_TIMEOUT_SECONDS=20
python -m startup_founder_email --project-root . validate
```

Validation behavior with Reacher enabled:

- `smtp_probe_status` values:
  - `deliverable` when Reacher reports deliverable mailbox.
  - `undeliverable` when mailbox is disabled/full or explicitly non-deliverable.
  - `catch_all` when domain accepts all recipients.
  - `error` on probe transport/parsing failures.
  - `skipped` when probe is not attempted (for example feature disabled or invalid syntax).
- `validation_notes` keeps offline checks and adds probe notes such as
  `smtp_probe_deliverable`, `smtp_probe_undeliverable`, `smtp_probe_catch_all`,
  or `smtp_probe_http_error`.

## Project layout

```text
src/startup_founder_email/
  __init__.py
  __main__.py
  cli.py
  config.py
  logging_utils.py
  models.py
  paths.py
  pipeline.py
  stages/
tests/
data/
  raw/
  normalized/
  enriched/
  generated/
  exported/
  logs/
```

## Codebase tour

This section is here to help you learn the project by reading the files in a sensible
order. The idea is that each file has one main job, and the important functions are
named so they explain themselves.

### `src/startup_founder_email/__main__.py`

This is the package entrypoint that makes `python3 -m startup_founder_email` work.

Important behavior:

- `main()`
  Imported from `cli.py` and executed when you run the package as a module.

Why it matters:

It gives the project a standard Python entrypoint without putting startup logic all
over the codebase.

### `src/startup_founder_email/cli.py`

This file is the command-line control layer. It decides which pipeline stage should
run and sets up the shared runtime context.

Important functions:

- `build_argument_parser()`
  Creates the top-level CLI parser and registers the available pipeline stages.

- `_add_stage_parser()`
  A small helper that keeps the parser setup readable by avoiding repeated code.

- `determine_stage_runner(stage_name)`
  Maps a stage name like `collect` or `normalize` to the Python function that should
  handle that stage.

- `main(argv=None)`
  The main program flow. It configures logging, parses arguments, builds pipeline
  context, and then calls the selected stage function.

Why it matters:

This file is like an air traffic controller. It routes work to the right stage, but
it does not do the stage's job itself.

### `src/startup_founder_email/config.py`

This file defines the configuration objects used across the pipeline.

Important classes:

- `RequestTimingConfig`
  Stores polite request settings such as delay ranges, timeout length, and retry count.

- `CollectorConfig`
  Stores source-collection settings such as the YC companies URL and the user-agent string.

- `OutputDirectoryConfig`
  Stores the standard folder locations used by the pipeline.

- `PipelineConfig`
  Groups the other config objects into one shared application config.

Important functions:

- `build_output_directory_config(project_root)`
  Builds the expected `data/raw`, `data/normalized`, `data/enriched`, and other paths.

- `load_pipeline_config(project_root)`
  Creates the app's full config object using readable defaults.

Why it matters:

Centralized config keeps behavior explicit. Instead of hunting for magic values across
the codebase, you can find the important settings in one place.

### `src/startup_founder_email/logging_utils.py`

This file sets up logging.

Important functions:

- `configure_logging()`
  Defines the default log format, timestamp format, and log level used by the app.

Why it matters:

Scraping and data pipelines get much easier to debug when log lines are consistent and readable.

### `src/startup_founder_email/models.py`

This file defines the typed records that move through the pipeline.

Important classes:

- `RawCompanyRecord`
  Represents a source record exactly as it was collected, including the raw payload
  and the raw company description from the source.

- `NormalizedFounderRecord`
  Represents a cleaned founder row after parsing and normalization, including the
  cleaned company description.

- `DomainEnrichmentRecord`
  Represents the same company/founder row after domain and MX metadata have been added.

- `ContactCandidateRecord`
  Represents the outreach-oriented output row, including public emails, inferred
  email guesses, the raw company description, and a shorter company summary for drafting.

Why it matters:

This is one of the most important files in the project. A good data pipeline usually
has clear record shapes for each stage, and these models make those shapes explicit.

### `src/startup_founder_email/paths.py`

This file contains small filesystem helpers.

Important functions:

- `ensure_output_directories_exist(output_directories)`
  Creates the standard pipeline directories if they do not already exist.

Why it matters:

Each stage should be able to assume its folders are ready. That removes a whole class
of avoidable errors.

### `src/startup_founder_email/pipeline.py`

This file handles shared pipeline setup.

Important classes:

- `PipelineContext`
  A small shared object that carries the project root and loaded config into each stage.

Important functions:

- `build_pipeline_context(project_root)`
  Loads config, ensures the directory structure exists, and returns a consistent
  context object for stage execution.

Why it matters:

This keeps startup logic in one place and avoids passing lots of unrelated values
through every stage call.

### `src/startup_founder_email/stages/collect.py`

This file handles raw page collection.

Important functions:

- `run_collection_stage(context)`
  Saves raw Firecrawl-shaped page records to `data/raw/items.jsonl`.

- `collect_live_firecrawl_page_records(...)`
  Scrapes configured target URLs through Firecrawl's synchronous `/v1/scrape` endpoint.

Why it matters:

Collection is about acquisition only. It should fetch and store source data before any
cleaning or enrichment happens.

### `src/startup_founder_email/stages/normalize.py`

This file is reserved for Phase 3.

Important functions:

- `run_normalization_stage(context)`
  Will convert raw source records into cleaned founder/company rows with stable fields.

Why it matters:

This is where messy source data becomes predictable enough for downstream processing.

### `src/startup_founder_email/stages/enrich.py`

This file is reserved for Phase 4.

Important functions:

- `run_enrichment_stage(context)`
  Will add canonical-domain, redirect, and MX metadata to normalized rows.

Why it matters:

Enrichment is a separate concern from collection. It adds external facts to already-clean data.

### `src/startup_founder_email/stages/generate.py`

This file is reserved for Phase 5.

Important functions:

- `run_contact_generation_stage(context)`
  Will prefer public emails when present, otherwise generate ranked work-email guesses
  and a short company summary for outreach drafting.

Why it matters:

This stage turns structured company/founder data into contact candidates you can use manually.

### `src/startup_founder_email/stages/export.py`

This file is reserved for Phase 6.

Important functions:

- `run_export_stage(context)`
  Will write the final review CSV and any operator-friendly outputs.

Why it matters:

Export is the stage that turns the pipeline's internal records into something you can
actually work from day to day.

### `tests/`

This folder contains lightweight tests for the scaffold.

Important files:

- `test_cli.py`
  Checks the CLI parser and stage lookup behavior.

- `test_config.py`
  Checks that configuration loading builds the expected paths and defaults.

- `test_models.py`
  Checks that the data models behave as expected, including the new description fields.

- `test_paths.py`
  Checks that the standard output directories can be created correctly.

Why it matters:

Even early tests are valuable because they lock in the shape of the system while the
project is still small and easy to reason about.

## Teaching note

In a data pipeline, "raw" data means "store what you got back from the source before
you start cleaning it." That matters because once parsing logic changes, you can
reprocess the saved raw input without hitting the network again.
