import { api } from "./api";
import { requireRealAudit } from "./real-audit";
import { SCHEMA_VERSION } from "./types";

export function auditIdFromUrl(href: string): string | null {
  const id = new URL(href).searchParams.get("audit");
  return id && /^run_[A-Za-z0-9_-]{1,120}$/.test(id) ? id : null;
}

export function auditUrl(href: string, id: string | null): string {
  const url = new URL(href);
  if (id) url.searchParams.set("audit", id);
  else url.searchParams.delete("audit");
  return `${url.pathname}${url.search}${url.hash}`;
}

/** Read an existing result. This path must never start a replacement audit. */
export async function restoreAudit(id: string, signal?: AbortSignal) {
  const result = await api.result(id, signal);
  if (result.run_id !== id || result.schema_version !== SCHEMA_VERSION)
    throw new Error("This audit could not be reopened with the current building service.");
  return requireRealAudit(result, result.property.sid);
}
