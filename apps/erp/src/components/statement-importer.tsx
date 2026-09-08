"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clientQuery } from "@/lib/client-query";

type Row = Record<string, unknown>;
const importsKey = ["statement-imports", { limit: 100 }] as const;
function value(row: Row, key: string) { return row[key] == null ? "—" : String(row[key]); }

export function StatementImporter() {
  const queryClient = useQueryClient();
  const [bankAccount, setBankAccount] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const imports = useQuery({ queryKey: importsKey, queryFn: () => clientQuery<Row[]>("/api/accounting/statement-imports?limit_page_length=100") });
  const create = useMutation({
    mutationFn: () => clientQuery<unknown>("/api/accounting/statement-imports", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bank_account: bankAccount, file: fileUrl }) }),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: importsKey }); setMessage("Đã tạo statement import log."); setBankAccount(""); setFileUrl(""); },
  });
  async function upload(file: File) {
    setUploading(true); setMessage(null);
    try { const body = new FormData(); body.append("file", file); const result = await clientQuery<Record<string, unknown>>(`/api/accounting/statement-imports/upload`, { method: "POST", body }); setFileUrl(String(result.file_url ?? "")); setMessage(`Đã upload ${file.name}.`); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Không thể upload file"); }
    finally { setUploading(false); }
  }
  const error = imports.error ?? create.error;
  const items = imports.data ?? [];
  return <div className="space-y-6"><section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">Create statement import</h2><p className="mt-1 text-sm text-muted-foreground">Upload CSV/PDF, chọn bank account rồi tạo import log.</p><div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_2fr_auto]"><input className="h-10 rounded-md border bg-background px-3" placeholder="Bank Account" value={bankAccount} onChange={(event) => setBankAccount(event.target.value)} /><input className="h-10 rounded-md border bg-background px-3 py-2 text-sm" type="file" accept=".csv,.pdf" disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); }} /><input className="h-10 rounded-md border bg-background px-3" placeholder="File URL" value={fileUrl} onChange={(event) => setFileUrl(event.target.value)} /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={!bankAccount || !fileUrl || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Đang tạo…" : "Create"}</button></div>{message ? <p className="mt-3 text-sm text-green-700">{message}</p> : null}{error ? <p className="mt-3 text-sm text-destructive">{error instanceof Error ? error.message : "Không thể tải import logs"}</p> : null}</section><section className="overflow-x-auto rounded-xl border bg-card"><table className="w-full text-sm"><thead className="bg-muted/50 text-left"><tr><th className="p-3">Name</th><th className="p-3">Bank account</th><th className="p-3">File</th><th className="p-3">Status</th></tr></thead><tbody>{items.map((item, index) => <tr className="border-t" key={String(item.name ?? index)}><td className="p-3"><Link className="text-primary hover:underline" href={`/accounts/statement-imports/${encodeURIComponent(String(item.name))}`}>{value(item, "name")}</Link></td><td className="p-3">{value(item, "bank_account")}</td><td className="p-3">{value(item, "file")}</td><td className="p-3">{value(item, "status")}</td></tr>)}</tbody></table>{!items.length && !imports.isPending ? <p className="p-10 text-center text-sm text-muted-foreground">Chưa có statement import log.</p> : null}</section></div>;
}
