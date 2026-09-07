"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AccountingResource } from "@/lib/letron-api";

const labels: Record<AccountingResource, string> = {
  banks: "Banks",
  "bank-accounts": "Bank Accounts",
  "bank-transactions": "Bank Transactions",
  "bank-transaction-rules": "Bank Transaction Rules",
  "cost-centers": "Cost Centers",
  "journal-entries": "Journal Entries",
  "modes-of-payment": "Modes of Payment",
  "payment-entries": "Payment Entries",
  "payment-orders": "Payment Orders",
  "payment-requests": "Payment Requests",
  "purchase-invoices": "Purchase Invoices",
  "sales-invoices": "Sales Invoices",
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function AccountingResourceTable({ resource, rows }: Readonly<{ resource: AccountingResource; rows: Record<string, unknown>[] }>) {
  const [query, setQuery] = useState("");
  const columns = useMemo(() => {
    const keys = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    return keys.filter((key) => !["doctype", "owner", "modified"].includes(key)).slice(0, 6);
  }, [rows]);
  const filtered = useMemo(() => rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query.toLowerCase())), [rows, query]);
  return <div className="rounded-xl border bg-card shadow-sm">
    <div className="flex flex-col gap-4 border-b p-5 sm:flex-row sm:items-center sm:justify-between">
      <div><h2 className="font-semibold">{labels[resource]}</h2><p className="text-sm text-muted-foreground">{filtered.length} of {rows.length} records</p></div>
      <Input className="w-full sm:max-w-xs" placeholder={`Search ${labels[resource].toLowerCase()}...`} value={query} onChange={(event) => setQuery(event.target.value)} />
    </div>
    <Table><TableHeader><TableRow>{columns.map((column) => <TableHead key={column}>{column.replaceAll("_", " ")}</TableHead>)}<TableHead>Status</TableHead></TableRow></TableHeader><TableBody>
      {filtered.map((row, index) => { const name = String(row.name ?? row.id ?? index); const disabled = Boolean(row.disabled); return <TableRow key={name}><>{columns.map((column) => <TableCell key={column}><Link className="hover:underline" href={`/accounts/${resource}/${encodeURIComponent(name)}`}>{displayValue(row[column])}</Link></TableCell>)}</><TableCell><Badge variant={disabled ? "secondary" : "default"}>{disabled ? "Disabled" : String(row.docstatus ?? "Active")}</Badge></TableCell></TableRow>; })}
    </TableBody></Table>
    {!filtered.length ? <div className="p-12 text-center text-sm text-muted-foreground">No records returned by the API.</div> : null}
  </div>;
}
