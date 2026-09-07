"use client";

import { useState } from "react";

const actions = [
  ["reconcile-vouchers", "Match / reconcile vouchers"],
  ["unreconcile-transaction", "Unreconcile transaction"],
  ["create-payment-entry", "Record payment"],
  ["create-internal-transfer", "Internal transfer"],
  ["create-bank-entry", "Record bank entry"],
  ["get-older-transactions", "Load older transactions"],
  ["set-closing-balance", "Set closing balance"],
] as const;

export function BankReconciliationActions() {
  const [action, setAction] = useState<(typeof actions)[number][0]>(actions[0][0]);
  const [payload, setPayload] = useState("{}");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setMessage(null); setError(null);
    try {
      const parsed = JSON.parse(payload) as unknown;
      const response = await fetch(`/api/accounting/bank-reconciliation/actions/${action}`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(parsed) });
      const body = await response.json().catch(() => ({})) as { data?: unknown; message?: unknown; exc_type?: string };
      if (!response.ok) throw new Error(typeof body.message === "string" ? body.message : body.exc_type ?? `HTTP ${response.status}`);
      setMessage(JSON.stringify(body.data ?? body.message ?? {}, null, 2));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể thực hiện reconciliation action"); }
    finally { setBusy(false); }
  }

  return <section className="rounded-xl border bg-card p-4"><div><h2 className="font-semibold">Reconciliation workflows</h2><p className="mt-1 text-sm text-muted-foreground">Các thao tác native của Bank Reconciliation Tool. Payload dùng đúng field ERPNext yêu cầu.</p></div><div className="mt-4 grid gap-3 md:grid-cols-[1fr_2fr_auto]"><select className="h-10 rounded-md border bg-background px-3" value={action} onChange={(event) => setAction(event.target.value as typeof action)}>{actions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><textarea className="min-h-24 rounded-md border bg-background p-3 font-mono text-xs" value={payload} onChange={(event) => setPayload(event.target.value)} aria-label="ERPNext action payload" /><button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={busy} onClick={run}>{busy ? "Đang chạy…" : "Run"}</button></div>{error ? <p className="mt-3 rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}{message ? <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">{message}</pre> : null}</section>;
}
