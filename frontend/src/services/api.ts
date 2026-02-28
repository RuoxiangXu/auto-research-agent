import type { SSEEvent, ReportSummary, ReportDetail } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// ── SSE streaming ───────────────────────────────────────────────────────────

export async function runResearchStream(
  payload: { topic: string; search_api?: string },
  onEvent: (event: SSEEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const response = await fetch(`${BASE_URL}/research/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Request failed (${response.status}): ${err}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;

      const jsonStr = trimmed.slice(5).trim();
      if (!jsonStr) continue;

      try {
        const event: SSEEvent = JSON.parse(jsonStr);
        onEvent(event);
      } catch {
        // skip malformed JSON
      }
    }
  }

  // process remaining buffer
  if (buffer.trim().startsWith("data:")) {
    const jsonStr = buffer.trim().slice(5).trim();
    if (jsonStr) {
      try {
        onEvent(JSON.parse(jsonStr));
      } catch {
        // skip
      }
    }
  }
}

// ── Report history API ──────────────────────────────────────────────────────

export async function fetchReports(): Promise<ReportSummary[]> {
  const res = await fetch(`${BASE_URL}/reports`);
  if (!res.ok) throw new Error("Failed to fetch reports");
  const data = await res.json();
  return data.reports;
}

export async function fetchReport(id: string): Promise<ReportDetail> {
  const res = await fetch(`${BASE_URL}/reports/${id}`);
  if (!res.ok) throw new Error("Report not found");
  return res.json();
}

export async function deleteReport(id: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/reports/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete report");
}
