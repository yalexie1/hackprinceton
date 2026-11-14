import type {
  DocumentDraft,
  DocumentRequest,
  PropertySummary,
  RunEvent,
  RunRequest,
  RunResult,
} from "./types";
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${base}/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      body?.error?.message ||
        `Request failed (${response.status}). Check that the backend is running.`,
    );
  }
  return response.json() as Promise<T>;
}
export const api = {
  health: () =>
    request<{ status: string; schema_version: string }>("/health", {
      signal: AbortSignal.timeout(6000),
    }),
  search: (query: string, segment: string, signal?: AbortSignal) =>
    request<PropertySummary[]>(
      `/properties/search?${new URLSearchParams({ q: query, ...(segment ? { segment } : {}), limit: "30" })}`,
      { signal },
    ),
  start: (body: RunRequest) =>
    request<{ run_id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  result: (id: string) => request<RunResult>(`/runs/${encodeURIComponent(id)}`),
  answer: (id: string, question_id: string, value: unknown) =>
    request<{ ok: boolean }>(`/runs/${encodeURIComponent(id)}/answers`, {
      method: "POST",
      body: JSON.stringify({ question_id, value }),
    }),
  update: (
    id: string,
    body: {
      budget_usd?: number;
      overrides?: Record<string, string | number | boolean>;
    },
  ) =>
    request<{ ok: boolean }>(`/runs/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  draft: (body: DocumentRequest) =>
    request<DocumentDraft>(
      `/runs/${encodeURIComponent(body.run_id)}/documents`,
      { method: "POST", body: JSON.stringify(body) },
    ),
};
// Incremental parser preserves split UTF-8, split CRLF, comments, and multiline data.
export function sseParser(onEvent: (event: RunEvent) => void) {
  let buffer = "";
  return (chunk: string, final = false) => {
    buffer += chunk;
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    if (final && buffer.trim()) {
      blocks.push(buffer);
      buffer = "";
    }
    for (const block of blocks) {
      const lines = block.split(/\r?\n/);
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).replace(/^ /, ""))
        .join("\n");
      if (!data || data === "[DONE]") continue;
      const parsed = JSON.parse(data);
      const eventType = lines
        .find((line) => line.startsWith("event:"))
        ?.slice(6)
        .trim();
      onEvent({
        ...parsed,
        type: parsed.type || eventType,
        message: parsed.message || "",
        payload: parsed.payload || {},
      });
    }
  };
}
export async function streamRun(
  id: string,
  onEvent: (event: RunEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(
    `${base}/api/runs/${encodeURIComponent(id)}/events`,
    { headers: { Accept: "text/event-stream" }, signal },
  );
  if (!response.ok || !response.body)
    throw new Error(`Could not open audit stream (${response.status}).`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let terminal = false;
  const consume = sseParser((event) => {
    onEvent(event);
    if (
      event.type === "done" ||
      event.type === "question" ||
      event.type === "error"
    )
      terminal = true;
  });
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        consume(decoder.decode(), true);
        break;
      }
      consume(decoder.decode(value, { stream: true }));
      if (terminal) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
}
export function assetUrl(path: string) {
  return `${base}/api/assets/${path.split("/").filter(Boolean).map(encodeURIComponent).join("/")}`;
}
