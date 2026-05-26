export type JobRecord = {
  job_id: string;
  status: string;
  seed_urls: string[];
  collection_mode: string;
  scrape_json_extract?: boolean;
  created_at_iso: string;
  updated_at_iso: string;
  page_count: number;
  error_message: string | null;
  stages_completed: string[];
};

export type ContactRow = Record<string, string> & {
  row_id: string;
};

export type ContactsResponse = {
  total: number;
  columns: string[];
  items: ContactRow[];
  csv_path: string;
};

export async function createCollectJob(
  seedUrls: string[],
  collectionMode: "crawl" | "scrape",
  scrapeJsonExtract: boolean,
): Promise<JobRecord> {
  const response = await fetch("/api/jobs/collect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      seed_urls: seedUrls,
      collection_mode: collectionMode,
      scrape_json_extract: scrapeJsonExtract,
    }),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<JobRecord>;
}

export async function getJob(jobId: string): Promise<JobRecord> {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<JobRecord>;
}

export async function runPipeline(jobId: string): Promise<JobRecord> {
  const response = await fetch(`/api/jobs/${jobId}/pipeline`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<JobRecord>;
}

export async function listContacts(jobId: string): Promise<ContactsResponse> {
  const query = new URLSearchParams({ job_id: jobId, limit: "500" });
  const response = await fetch(`/api/contacts?${query.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<ContactsResponse>;
}

export async function patchContact(
  jobId: string,
  rowId: string,
  updates: Partial<Pick<ContactRow, "best_email_guess" | "public_email_address" | "notes" | "status">>,
): Promise<ContactRow> {
  const query = new URLSearchParams({ job_id: jobId });
  const response = await fetch(`/api/contacts/${rowId}?${query.toString()}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<ContactRow>;
}

export function buildContactsCsvDownloadUrl(jobId: string): string {
  const query = new URLSearchParams({ job_id: jobId });
  return `/api/contacts/export.csv?${query.toString()}`;
}
