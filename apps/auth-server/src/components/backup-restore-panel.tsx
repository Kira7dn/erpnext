"use client";

import { useEffect, useState } from "react";

type Backup = { timestamp: string; dateStr: string; totalSizeHuman: string; fileCount: number; isCompliant: boolean };

export function BackupRestorePanel() {
  const [items, setItems] = useState<Backup[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await fetch("/api/backup/list?limit=10", { cache: "no-store" });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error ?? "Không thể tải danh sách backup");
    setItems(body.items ?? []);
    setSelected((current) => current || body.items?.[0]?.timestamp || "");
  }

  useEffect(() => { const timer = window.setTimeout(() => { void load().catch((cause) => setError(cause instanceof Error ? cause.message : "Không thể tải backup")); }, 0); return () => window.clearTimeout(timer); }, []);

  async function restore(mode: "drill" | "live") {
    if (!selected) return;
    setBusy(true); setError(null); setMessage(null);
    try {
      const response = await fetch("/api/backup/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ timestamp: selected, mode }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error ?? "Không thể khôi phục backup");
      setMessage(body.message ?? "Đã gửi yêu cầu khôi phục.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Không thể khôi phục backup"); }
    finally { setBusy(false); }
  }

  return <section className="mt-12 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"><div><h2 className="text-2xl font-bold text-slate-950">Sao lưu & Khôi phục</h2><p className="mt-1 text-sm text-slate-500">Quản lý backup ERPNext và thực hiện Restore Drill từ S3.</p></div><div className="mt-5 flex flex-col gap-3 sm:flex-row"><select className="h-10 min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 text-sm" value={selected} onChange={(event) => setSelected(event.target.value)} disabled={!items.length}>{items.length ? items.map((item) => <option key={item.timestamp} value={item.timestamp}>{item.dateStr} · {item.totalSizeHuman} · {item.fileCount} files{item.isCompliant ? " · compliant" : " · incomplete"}</option>) : <option>Không có backup</option>}</select><button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || !selected} onClick={() => void restore("drill")} type="button">{busy ? "Đang xử lý…" : "Restore Drill"}</button><button className="rounded-lg border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-50" disabled={busy || !selected} onClick={() => { if (window.confirm("Xác nhận gửi yêu cầu restore live?")) void restore("live"); }} type="button">Restore live</button></div>{message ? <p className="mt-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p> : null}{error ? <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}</section>;
}
