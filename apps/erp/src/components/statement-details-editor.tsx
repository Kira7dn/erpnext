"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clientQuery } from "@/lib/client-query";

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
  const queryClient = useQueryClient();
  const mutation = useMutation({ mutationFn: (body: unknown) => clientQuery(`/api/accounting/statement-imports/${encodeURIComponent(name)}/${operation}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["statement-imports"] }); setMessage("Đã cập nhật statement details."); } });
  async function save() { setError(null); setMessage(null); try { const parsed = JSON.parse(payload) as unknown; await mutation.mutateAsync(parsed); } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể cập nhật statement details"); } }
  return <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">CSV/PDF statement editor</h2><p className="mt-1 text-sm text-muted-foreground">Thực thi các thao tác mapping và chỉnh bảng native của Bank Statement Import Log.</p><div className="mt-4 grid gap-3 md:grid-cols-[1fr_2fr_auto]"><select className="h-10 rounded-md border bg-background px-3" value={operation} onChange={(event) => setOperation(event.target.value as typeof operation)}>{operations.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><textarea className="min-h-48 rounded-md border bg-background p-3 font-mono text-xs" value={payload} onChange={(event) => setPayload(event.target.value)} /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={mutation.isPending} onClick={() => void save()}>{mutation.isPending ? "Đang lưu…" : "Save"}</button></div>{error ? <p className="mt-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}{message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}</section>;
}
