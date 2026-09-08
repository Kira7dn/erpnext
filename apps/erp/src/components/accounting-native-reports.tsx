"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { clientQuery } from "@/lib/client-query";

type Row = Record<string, unknown>;
const reports = [["bank-reconciliation-statement", "Bank Reconciliation Statement"], ["bank-clearance-summary", "Bank Clearance Summary"], ["incorrectly-cleared", "Incorrectly Cleared Entries"]] as const;
type ReportKey = typeof reports[number][0];

export function AccountingNativeReports() {
  const [report, setReport] = useState<ReportKey>(reports[0][0]);
  const [filters, setFilters] = useState('{"company":"Letron Việt Nam"}');
  const query = useQuery({ queryKey: ["accounting-report", report, filters], enabled: false, queryFn: async () => { const params = new URLSearchParams({ report_key: report, filters }); const payload = await clientQuery<Record<string, unknown>>(`/api/accounting/reports/report?${params}`); const data = (payload.result ?? payload.data ?? {}) as { result?: unknown; data?: unknown; columns?: unknown }; const rawResult = data.result ?? data.data; const result: Row[] = Array.isArray(rawResult) ? rawResult as Row[] : []; const columns = Array.isArray(data.columns) ? data.columns.map((column: string | { fieldname?: string; label?: string }) => typeof column === "string" ? column : column.label ?? column.fieldname ?? "Column") : result[0] ? Object.keys(result[0]) : []; return { rows: result, columns }; } });
  async function run() { await query.refetch(); }
  const rows = query.data?.rows ?? []; const columns = query.data?.columns ?? [];
  return <div className="space-y-5"><div className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1fr_2fr_auto]"><select className="h-10 rounded-md border bg-background px-3" value={report} onChange={(event) => setReport(event.target.value as ReportKey)}>{reports.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input className="h-10 rounded-md border bg-background px-3 font-mono text-sm" value={filters} onChange={(event) => setFilters(event.target.value)} aria-label="Report filters JSON" /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" disabled={query.isFetching} onClick={() => void run()}>{query.isFetching ? "Đang chạy…" : "Run report"}</button></div>{query.error ? <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{query.error instanceof Error ? query.error.message : "Không thể chạy report"}</p> : null}<div className="overflow-x-auto rounded-xl border bg-card">{rows.length ? <table className="w-full text-sm"><thead className="bg-muted/50 text-left"><tr>{columns.map((column) => <th className="whitespace-nowrap p-3" key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr className="border-t" key={String(row.name ?? index)}>{columns.map((column) => <td className="whitespace-nowrap p-3" key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table> : <p className="p-10 text-center text-sm text-muted-foreground">Chọn report và Run để tải dữ liệu live.</p>}</div></div>;
}
