"use client";

import { useState } from "react";

type Row = Record<string, unknown>;
const reports = [["bank-reconciliation-statement", "Bank Reconciliation Statement"], ["bank-clearance-summary", "Bank Clearance Summary"], ["incorrectly-cleared", "Incorrectly Cleared Entries"]] as const;
type ReportKey = typeof reports[number][0];

export function AccountingNativeReports() {
  const [report, setReport] = useState<ReportKey>(reports[0][0]);
  const [filters, setFilters] = useState('{"company":"Letron Việt Nam"}');
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  async function run() {
    setLoading(true); setError(null);
    try {
      const query = new URLSearchParams({ report_key: report, filters });
      const response = await fetch(`/api/accounting/reports/report?${query}`, { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.message ?? payload.exc_type ?? `HTTP ${response.status}`);
      const data = payload.data ?? payload.message ?? {};
      const result = data.result ?? data.data ?? [];
      setRows(Array.isArray(result) ? result : []);
      setColumns(Array.isArray(data.columns) ? data.columns.map((column: string | { fieldname?: string; label?: string }) => typeof column === "string" ? column : column.label ?? column.fieldname ?? "Column") : Array.isArray(result) && result[0] ? Object.keys(result[0]) : []);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể chạy report"); }
    finally { setLoading(false); }
  }
  return <div className="space-y-5"><div className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1fr_2fr_auto]"><select className="h-10 rounded-md border bg-background px-3" value={report} onChange={(event) => setReport(event.target.value as ReportKey)}>{reports.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input className="h-10 rounded-md border bg-background px-3 font-mono text-sm" value={filters} onChange={(event) => setFilters(event.target.value)} aria-label="Report filters JSON" /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" disabled={loading} onClick={run}>{loading ? "Đang chạy…" : "Run report"}</button></div>{error ? <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}<div className="overflow-x-auto rounded-xl border bg-card">{rows.length ? <table className="w-full text-sm"><thead className="bg-muted/50 text-left"><tr>{columns.map((column) => <th className="whitespace-nowrap p-3" key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr className="border-t" key={index}>{columns.map((column) => <td className="whitespace-nowrap p-3" key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table> : <p className="p-10 text-center text-sm text-muted-foreground">Chọn report và Run để tải dữ liệu live.</p>}</div></div>;
}
