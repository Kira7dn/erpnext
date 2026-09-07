"use client";

import { useState } from "react";

const operations = [
  ["update-pdf-tables", "Save PDF tables"],
  ["reextract-pdf-table", "Re-extract PDF table"],
  ["set-pdf-table-header", "Set PDF header"],
  ["update-column-mapping", "Update column mapping"],
  ["set-header-index", "Set CSV header index"],
] as const;

export function StatementDetailsEditor({ name, initialDetails }: Readonly<{ name: string; initialDetails: unknown }>) {
  const [operation, setOperation] = useState<(typeof operations)[number][0]>(operations[0][0]);
  const [payload, setPayload] = useState(JSON.stringify(initialDetails ?? {}, null, 2));
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() { setBusy(true); setError(null); setMessage(null); try { const parsed = JSON.parse(payload) as unknown; const response = await fetch(`/api/accounting/statement-imports/${encodeURIComponent(name)}/${operation}`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(parsed) }); const body = await response.json(); if (!response.ok) throw new Error(body.message ?? body.exc_type ?? `HTTP ${response.status}`); setMessage("Đã cập nhật statement details."); } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể cập nhật statement details"); } finally { setBusy(false); } }
  return <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">CSV/PDF statement editor</h2><p className="mt-1 text-sm text-muted-foreground">Thực thi các thao tác mapping và chỉnh bảng native của Bank Statement Import Log.</p><div className="mt-4 grid gap-3 md:grid-cols-[1fr_2fr_auto]"><select className="h-10 rounded-md border bg-background px-3" value={operation} onChange={(event) => setOperation(event.target.value as typeof operation)}>{operations.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><textarea className="min-h-48 rounded-md border bg-background p-3 font-mono text-xs" value={payload} onChange={(event) => setPayload(event.target.value)} /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : "Save"}</button></div>{error ? <p className="mt-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}{message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}</section>;
}
