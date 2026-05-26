import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  buildContactsCsvDownloadUrl,
  ContactRow,
  ContactsResponse,
  createCollectJob,
  getJob,
  JobRecord,
  listContacts,
  patchContact,
  runPipeline,
} from "./api";

type ActiveTab = "run" | "contacts";

const DISPLAY_COLUMN_LABELS: Record<string, string> = {
  founder_full_name: "Founder",
  company_name: "Company",
  company_website_url: "Website",
  canonical_company_domain: "Domain",
  public_email_address: "Public email",
  best_email_guess: "Best email",
  alternative_email_guess: "Alt email",
  email_source_type: "Email source",
  email_confidence_level: "Confidence",
  company_summary: "Summary",
  source_url: "Source page",
  smtp_probe_status: "SMTP probe",
  validation_notes: "Validation",
  status: "Status",
  notes: "Notes",
};

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("run");
  const [seedUrlsText, setSeedUrlsText] = useState("https://texsoftware.com");
  const [collectionMode, setCollectionMode] = useState<"crawl" | "scrape">("crawl");
  const [scrapeJsonExtract, setScrapeJsonExtract] = useState(false);
  const [currentJob, setCurrentJob] = useState<JobRecord | null>(null);
  const [jobMessage, setJobMessage] = useState("");
  const [contactsData, setContactsData] = useState<ContactsResponse | null>(null);
  const [contactsMessage, setContactsMessage] = useState("");

  const loadContacts = useCallback(async (jobIdOverride?: string) => {
    const jobId = jobIdOverride ?? currentJob?.job_id;
    if (!jobId) {
      setContactsData(null);
      setContactsMessage("Run a job before reviewing contacts.");
      return;
    }

    try {
      const response = await listContacts(jobId);
      setContactsData(response);
      setContactsMessage(
        response.total === 0
          ? "This job's contacts.csv has no data rows yet. Run collect + pipeline, or enable AI extraction for tricky sites."
          : `Showing ${response.items.length} of ${response.total} rows from this job's contacts.csv`,
      );
    } catch (error) {
      setContactsMessage(String(error));
      setContactsData(null);
    }
  }, [currentJob?.job_id]);

  useEffect(() => {
    if (activeTab === "contacts") {
      void loadContacts();
    }
  }, [activeTab, loadContacts]);

  useEffect(() => {
    if (!currentJob) {
      return;
    }
    if (currentJob.status === "error" || currentJob.status === "done") {
      if (currentJob.status === "done") {
        void loadContacts(currentJob.job_id);
      }
      return;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const updatedJob = await getJob(currentJob.job_id);
        setCurrentJob(updatedJob);
        if (updatedJob.status === "collect_completed") {
          setJobMessage(
            `Collect finished with ${updatedJob.page_count} pages. Run pipeline to process contacts.`,
          );
        }
        if (updatedJob.status === "done") {
          setJobMessage("Pipeline finished. Review contacts below or on the Contacts tab.");
          void loadContacts(updatedJob.job_id);
        }
        if (updatedJob.status === "error") {
          setJobMessage(updatedJob.error_message ?? "Job failed.");
        }
      } catch (error) {
        setJobMessage(String(error));
      }
    }, 3000);

    return () => window.clearInterval(intervalId);
  }, [currentJob, loadContacts]);

  async function handleStartCollect(event: FormEvent) {
    event.preventDefault();
    const seedUrls = seedUrlsText
      .split(/[\n,]+/)
      .map((seedUrl) => seedUrl.trim())
      .filter(Boolean);
    if (seedUrls.length === 0) {
      setJobMessage("Add at least one seed URL.");
      return;
    }

    try {
      setJobMessage("Starting collect job...");
      const job = await createCollectJob(seedUrls, collectionMode, scrapeJsonExtract);
      setCurrentJob(job);
      setContactsData(null);
      setContactsMessage("");
      setJobMessage(
        `Job ${job.job_id} started (${job.collection_mode}${job.scrape_json_extract ? ", AI extraction on" : ""}).`,
      );
    } catch (error) {
      setJobMessage(String(error));
    }
  }

  async function handleRunPipeline() {
    if (!currentJob) {
      return;
    }
    try {
      setJobMessage("Running normalize → export...");
      const job = await runPipeline(currentJob.job_id);
      setCurrentJob(job);
    } catch (error) {
      setJobMessage(String(error));
    }
  }

  async function handleContactEmailSave(contact: ContactRow, bestEmailGuess: string) {
    if (!currentJob) {
      setContactsMessage("Run a job before editing contacts.");
      return;
    }

    try {
      const updatedContact = await patchContact(currentJob.job_id, contact.row_id, {
        best_email_guess: bestEmailGuess,
      });
      setContactsData((existing) => {
        if (!existing) {
          return existing;
        }
        return {
          ...existing,
          items: existing.items.map((existingContact) =>
            existingContact.row_id === updatedContact.row_id
              ? updatedContact
              : existingContact,
          ),
        };
      });
    } catch (error) {
      setContactsMessage(String(error));
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Startup Founder Email</h1>
          <p>Crawl startup sites, extract founders, and review outreach contacts.</p>
        </div>
        <nav className="tabs">
          <button
            type="button"
            className={activeTab === "run" ? "tab active" : "tab"}
            onClick={() => setActiveTab("run")}
          >
            Run
          </button>
          <button
            type="button"
            className={activeTab === "contacts" ? "tab active" : "tab"}
            onClick={() => setActiveTab("contacts")}
          >
            Contacts
            {contactsData && contactsData.total > 0 ? ` (${contactsData.total})` : ""}
          </button>
        </nav>
      </header>

      {activeTab === "run" ? (
        <section className="panel">
          <form onSubmit={handleStartCollect}>
            <label className="field">
              <span>Seed URLs (one per line or comma-separated)</span>
              <textarea
                value={seedUrlsText}
                onChange={(event) => setSeedUrlsText(event.target.value)}
                rows={6}
              />
            </label>
            <label className="field">
              <span>Collection mode</span>
              <select
                value={collectionMode}
                onChange={(event) =>
                  setCollectionMode(event.target.value as "crawl" | "scrape")
                }
              >
                <option value="crawl">crawl (recommended)</option>
                <option value="scrape">scrape (single page per URL)</option>
              </select>
            </label>

            <fieldset className="extraction-options">
              <legend>Founder extraction</legend>
              <label className="extraction-option">
                <input
                  type="radio"
                  name="extraction-mode"
                  checked={!scrapeJsonExtract}
                  onChange={() => setScrapeJsonExtract(false)}
                />
                <span>
                  <strong>Standard parsing only</strong>
                  <small>Fast. Works when pages list founders like “Name, CEO”.</small>
                </span>
              </label>
              <label className="extraction-option extraction-option--ai">
                <input
                  type="radio"
                  name="extraction-mode"
                  checked={scrapeJsonExtract}
                  onChange={() => setScrapeJsonExtract(true)}
                />
                <span>
                  <strong>AI extraction (Ollama via Firecrawl)</strong>
                  <small>
                    Use for tricky sites (e.g. terac.com). Slower; needs Firecrawl + Ollama
                    running.
                  </small>
                </span>
              </label>
            </fieldset>
            <div className="actions">
              <button type="submit">Start collect</button>
              <button
                type="button"
                onClick={() => void handleRunPipeline()}
                disabled={
                  !currentJob ||
                  !["collect_completed", "done", "processing"].includes(currentJob.status)
                }
              >
                Run pipeline
              </button>
            </div>
          </form>

          {currentJob ? (
            <div className="job-card">
              <h2>Job {currentJob.job_id}</h2>
              <p>
                <strong>Status:</strong> {currentJob.status}
              </p>
              <p>
                <strong>Pages collected:</strong> {currentJob.page_count}
              </p>
              <p>
                <strong>AI extraction:</strong>{" "}
                {currentJob.scrape_json_extract === true
                  ? "enabled"
                  : currentJob.scrape_json_extract === false
                    ? "disabled"
                    : "unknown"}
              </p>
              {currentJob.scrape_json_extract === undefined ? (
                <p className="error">
                  This API build does not report AI extraction. Stop the server, run{" "}
                  <code>pip install -e &quot;.[api,dev]&quot;</code>, restart{" "}
                  <code>startup-founder-email-api --project-root .</code>, then start a new
                  collect with AI extraction selected.
                </p>
              ) : null}
              <p>
                <strong>Stages completed:</strong>{" "}
                {currentJob.stages_completed.length > 0
                  ? currentJob.stages_completed.join(", ")
                  : "none"}
              </p>
              {currentJob.error_message ? (
                <p className="error">{currentJob.error_message}</p>
              ) : null}
            </div>
          ) : null}
          {jobMessage ? <p className="message">{jobMessage}</p> : null}

          {contactsData && contactsData.total > 0 ? (
            <ContactsSection
              contactsData={contactsData}
              contactsMessage={contactsMessage}
              jobId={currentJob?.job_id ?? null}
              onRefresh={loadContacts}
              onSaveEmail={handleContactEmailSave}
              compact
            />
          ) : null}
        </section>
      ) : (
        <ContactsSection
          contactsData={contactsData}
          contactsMessage={contactsMessage}
          jobId={currentJob?.job_id ?? null}
          onRefresh={loadContacts}
          onSaveEmail={handleContactEmailSave}
        />
      )}
    </div>
  );
}

function ContactsSection({
  contactsData,
  contactsMessage,
  jobId,
  onRefresh,
  onSaveEmail,
  compact = false,
}: {
  contactsData: ContactsResponse | null;
  contactsMessage: string;
  jobId: string | null;
  onRefresh: () => Promise<void>;
  onSaveEmail: (contact: ContactRow, bestEmailGuess: string) => Promise<void>;
  compact?: boolean;
}) {
  const columns =
    contactsData?.columns.filter((column) => column !== "row_id") ?? [];

  return (
    <section className={compact ? "contacts-panel contacts-panel--compact" : "contacts-panel"}>
      {!compact ? <h2>contacts.csv</h2> : <h3>Exported contacts</h3>}
      <div className="actions">
        <button type="button" onClick={() => void onRefresh()}>
          Refresh
        </button>
        {jobId ? (
          <a
            href={buildContactsCsvDownloadUrl(jobId)}
            className="button-link"
            download="contacts.csv"
          >
            Download CSV
          </a>
        ) : null}
      </div>
      {contactsData?.csv_path ? (
        <p className="csv-path">
          File: <code>{contactsData.csv_path}</code>
        </p>
      ) : null}
      {contactsMessage ? <p className="message">{contactsMessage}</p> : null}
      {contactsData && contactsData.total > 0 ? (
        <ContactsTable
          columns={columns}
          contacts={contactsData.items}
          onSaveEmail={onSaveEmail}
        />
      ) : (
        <p className="empty-state">
          No rows in contacts.csv yet. Run a collect job and pipeline from the Run tab.
        </p>
      )}
    </section>
  );
}

function ContactsTable({
  columns,
  contacts,
  onSaveEmail,
}: {
  columns: string[];
  contacts: ContactRow[];
  onSaveEmail: (contact: ContactRow, bestEmailGuess: string) => Promise<void>;
}) {
  return (
    <div className="table-wrap">
      <table className="contacts-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{DISPLAY_COLUMN_LABELS[column] ?? column}</th>
            ))}
            <th>Save email</th>
          </tr>
        </thead>
        <tbody>
          {contacts.map((contact) => (
            <ContactTableRow
              key={contact.row_id}
              columns={columns}
              contact={contact}
              onSaveEmail={onSaveEmail}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ContactTableRow({
  columns,
  contact,
  onSaveEmail,
}: {
  columns: string[];
  contact: ContactRow;
  onSaveEmail: (contact: ContactRow, bestEmailGuess: string) => Promise<void>;
}) {
  const [bestEmailGuess, setBestEmailGuess] = useState(contact.best_email_guess ?? "");

  return (
    <tr>
      {columns.map((column) => (
        <td key={column}>
          {column === "best_email_guess" ? (
            <input
              className="table-input"
              value={bestEmailGuess}
              onChange={(event) => setBestEmailGuess(event.target.value)}
            />
          ) : column === "source_url" && contact.source_url ? (
            <a href={contact.source_url} target="_blank" rel="noreferrer">
              {contact.source_url}
            </a>
          ) : column === "company_website_url" && contact.company_website_url ? (
            <a href={contact.company_website_url} target="_blank" rel="noreferrer">
              {contact.company_website_url}
            </a>
          ) : (
            contact[column] ?? ""
          )}
        </td>
      ))}
      <td>
        <button type="button" onClick={() => void onSaveEmail(contact, bestEmailGuess)}>
          Save
        </button>
      </td>
    </tr>
  );
}
