"use client";

import { useEffect, useState } from "react";

export function AccountsSettings() {
  const [value, setValue] = useState("{}");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; fetch("/api/accounting/settings", { headers: { Accept: "application/json" } }).then(async (response) => { const body = await response.json(); if (!response.ok) throw new Error(body.message ?? body.exc_type ?? `HTTP ${response.status}`); return body.data ?? body.message ?? {}; }).then((data) => { if (active) setValue(JSON.stringify(data, null, 2)); }).catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Không thể tải Accounts Settings"); }); return () => { active = false; }; }, []);
  async function save() { setBusy(true); setError(null); setMessage(null); try { const response = await fetch("/api/accounting/settings", { method: "PUT", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: value }); const body = await response.json(); if (!response.ok) throw new Error(body.message ?? body.exc_type ?? `HTTP ${response.status}`); setValue(JSON.stringify(body.data ?? body.message ?? {}, null, 2)); setMessage("Đã lưu Accounts Settings."); } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể lưu Accounts Settings"); } finally { setBusy(false); } }
  return <section className="space-y-4 rounded-xl border bg-card p-5"><div><h2 className="font-semibold">Accounts Settings</h2><p className="mt-1 text-sm text-muted-foreground">Đọc và cập nhật cấu hình native từ ERPNext. Các field hệ thống được backend bảo vệ.</p></div><textarea className="min-h-[32rem] w-full rounded-md border bg-background p-3 font-mono text-xs" value={value} onChange={(event) => setValue(event.target.value)} />{error ? <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}{message ? <p className="text-sm text-green-700">{message}</p> : null}<button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50" disabled={busy} onClick={save}>{busy ? "Đang lưu…" : "Save settings"}</button></section>;
}
