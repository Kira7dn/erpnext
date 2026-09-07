"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Row = Record<string, unknown>;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/accounting/${path}`, { ...init, headers: { Accept: "application/json", ...(init?.headers ?? {}) } });
  const payload = await response.json().catch(() => ({})) as { data?: T; message?: T; exc_type?: string };
  if (!response.ok) throw new Error(typeof payload.message === "string" ? payload.message : payload.exc_type ?? `HTTP ${response.status}`);
  return (payload.data ?? payload.message) as T;
}

function text(row: Row, ...keys: string[]) {
  const value = keys.map((key) => row[key]).find((item) => item !== undefined && item !== null && item !== "");
  return value === undefined ? "—" : String(value);
}

export function BankReconciliationWorkbench() {
  const [accounts, setAccounts] = useState<Row[]>([]);
  const [transactions, setTransactions] = useState<Row[]>([]);
  const [account, setAccount] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);
  const [linked, setLinked] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadTransactions() {
    if (!account) return;
    setBusy(true); setError(null);
    try {
      const query = new URLSearchParams({ bank_account: account });
      if (fromDate) query.set("from_date", fromDate);
      if (toDate) query.set("to_date", toDate);
      setTransactions(await request<Row[]>(`bank-reconciliation/transactions?${query}`));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể tải giao dịch"); }
    finally { setBusy(false); }
  }

  useEffect(() => { request<Row[]>("../bank-accounts?limit_page_length=100").then(setAccounts).catch((cause) => setError(cause instanceof Error ? cause.message : "Không thể tải tài khoản")); }, []);

  async function selectTransaction(row: Row) {
    setSelected(row); setLinked([]);
    const name = text(row, "name");
    if (name === "—") return;
    try { setLinked(await request<Row[]>(`bank-reconciliation/linked-payments?bank_transaction_name=${encodeURIComponent(name)}`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể tải payment liên kết"); }
  }

  async function clearClearance() {
    if (!selected) return;
    setBusy(true); setError(null);
    try {
      await request("bank-reconciliation/clear-clearance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ voucher_type: selected.voucher_type ?? "Bank Transaction", voucher_name: selected.name }) });
      await loadTransactions();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể xóa clearance"); }
    finally { setBusy(false); }
  }

  const reconciled = useMemo(() => transactions.filter((row) => String(row.status ?? "").toLowerCase().includes("reconcil") || Number(row.docstatus) === 1).length, [transactions]);
  return <div className="space-y-6">
    <section className="grid gap-3 rounded-xl border bg-card p-4 md:grid-cols-[2fr_1fr_1fr_auto]">
      <label className="grid gap-1 text-sm font-medium">Bank Account<select className="h-10 rounded-md border bg-background px-3 font-normal" value={account} onChange={(event) => setAccount(event.target.value)}><option value="">Chọn tài khoản</option>{accounts.map((item) => <option key={String(item.name)} value={String(item.name)}>{text(item, "account_name", "name")}</option>)}</select></label>
      <label className="grid gap-1 text-sm font-medium">From<input className="h-10 rounded-md border bg-background px-3 font-normal" type="date" value={fromDate} onChange={(event) => setFromDate(event.target.value)} /></label>
      <label className="grid gap-1 text-sm font-medium">To<input className="h-10 rounded-md border bg-background px-3 font-normal" type="date" value={toDate} onChange={(event) => setToDate(event.target.value)} /></label>
      <button className="mt-auto h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={!account || busy} onClick={loadTransactions}>{busy ? "Đang tải…" : "Load"}</button>
    </section>
    {error ? <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
    <div className="grid gap-4 sm:grid-cols-3"><Metric label="Transactions" value={transactions.length} /><Metric label="Reconciled" value={reconciled} /><Metric label="Unreconciled" value={transactions.length - reconciled} /></div>
    <section className="overflow-hidden rounded-xl border bg-card"><div className="border-b p-4"><h2 className="font-semibold">Bank transactions</h2><p className="text-sm text-muted-foreground">Chọn một dòng để xem payment liên kết và thao tác clearance.</p></div><div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-muted/50 text-left"><tr><th className="p-3">Date</th><th className="p-3">Description</th><th className="p-3">Deposit</th><th className="p-3">Withdrawal</th><th className="p-3">Status</th></tr></thead><tbody>{transactions.map((row, index) => <tr className={`cursor-pointer border-t hover:bg-muted/40 ${selected === row ? "bg-muted" : ""}`} key={String(row.name ?? index)} onClick={() => selectTransaction(row)}><td className="p-3">{text(row, "date", "posting_date")}</td><td className="p-3">{text(row, "description", "name")}</td><td className="p-3">{text(row, "deposit")}</td><td className="p-3">{text(row, "withdrawal")}</td><td className="p-3">{text(row, "status", "docstatus")}</td></tr>)}</tbody></table></div>{!transactions.length ? <p className="p-10 text-center text-sm text-muted-foreground">Chưa có giao dịch. Chọn bank account và Load.</p> : null}</section>
    {selected ? <section className="rounded-xl border bg-card p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">{text(selected, "name")}</h2><p className="text-sm text-muted-foreground">{text(selected, "description")}</p></div><div className="flex gap-2"><Link className="rounded-md border px-3 py-2 text-sm" href={`/accounts/bank-transactions/${encodeURIComponent(text(selected, "name"))}`}>Open</Link><button className="rounded-md border px-3 py-2 text-sm" disabled={busy} onClick={clearClearance}>Clear clearance</button></div></div><h3 className="mt-5 text-sm font-semibold">Linked payments</h3>{linked.length ? <ul className="mt-2 space-y-2 text-sm">{linked.map((row, index) => <li className="rounded-md border p-3" key={String(row.name ?? index)}>{text(row, "name", "payment_entry")} · {text(row, "allocated_amount", "amount")}</li>)}</ul> : <p className="mt-2 text-sm text-muted-foreground">Chưa có payment liên kết hoặc chưa tải được.</p>}</section> : null}
  </div>;
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="rounded-xl border bg-card p-4"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-bold">{value}</p></div>; }
