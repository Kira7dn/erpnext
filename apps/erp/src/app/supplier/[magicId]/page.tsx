"use client";

import { FormEvent, useEffect, useState } from "react";
import { publicErrorMessage, retryAfterSeconds } from "@/lib/error-contract";

type Item = { name: string; item_code: string; description: string; qty: number; uom: string; rate?: number };
type Summary = { supplier: string; rfq: { name: string; status: string; items: Item[] }; quotation: { name: string; status: string } | null; purchase_order: { name: string; status: string; currency: string; items: Item[] } | null; purchase_receipt: { name: string; status: string }[]; purchase_invoice: { name: string; status: string }[]; payment_status: string; approval_status: string; deadline_at: string };
type ApiPayload = { error?: unknown; retry_after_seconds?: unknown; resend_after_seconds?: unknown };

async function payloadOf(response: Response): Promise<ApiPayload> {
  return (await response.json().catch(() => ({}))) as ApiPayload;
}

function errorMessage(response: Response, payload: ApiPayload): string {
  return publicErrorMessage(payload.error, response.status);
}

export default function SupplierPortalPage({ params }: { params: Promise<{ magicId: string }> }) {
  const [magicId, setMagicId] = useState("");
  const [otp, setOtp] = useState("");
  const [sent, setSent] = useState(false);
  const [sendingOtp, setSendingOtp] = useState(false);
  const [otpCooldownUntil, setOtpCooldownUntil] = useState(0);
  const [otpCooldownSeconds, setOtpCooldownSeconds] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rates, setRates] = useState<Record<string, string>>({});
  const [deliveryDate, setDeliveryDate] = useState("");
  const [deliveryQty, setDeliveryQty] = useState<Record<string, string>>({});
  const [xmlFile, setXmlFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void params.then(({ magicId: value }) => setMagicId(value));
  }, [params]);

  useEffect(() => {
    if (!otpCooldownUntil) return;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((otpCooldownUntil - Date.now()) / 1000));
      setOtpCooldownSeconds(remaining);
      if (!remaining) setOtpCooldownUntil(0);
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [otpCooldownUntil]);

  async function refresh() {
    try {
      const response = await fetch("/api/supplier/session/process", { cache: "no-store" });
      if (!response.ok) {
        setMessage(errorMessage(response, await payloadOf(response)));
        return;
      }
      const payload = (await response.json()) as { data?: Summary };
      setSummary(payload.data ?? null);
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    }
  }

  async function requestOtp() {
    if (sendingOtp || !magicId || otpCooldownSeconds > 0) return;
    setSendingOtp(true);
    try {
      const response = await fetch(`/api/supplier/${encodeURIComponent(magicId)}/otp/request`, { method: "POST" });
      const payload = await payloadOf(response);
      const retryAfter = retryAfterSeconds(payload.retry_after_seconds) ?? retryAfterSeconds(response.headers.get("Retry-After"));
      if (response.ok) {
        setSent(true);
        setOtpCooldownUntil(Date.now() + (retryAfter ?? retryAfterSeconds(payload.resend_after_seconds) ?? 15) * 1000);
        setMessage("OTP đã được gửi tới email của Supplier.");
      } else {
        if (retryAfter) setOtpCooldownUntil(Date.now() + retryAfter * 1000);
        setMessage(errorMessage(response, payload));
      }
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    } finally {
      setSendingOtp(false);
    }
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch(`/api/supplier/${encodeURIComponent(magicId)}/otp/verify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ otp }) });
      if (!response.ok) {
        setMessage(errorMessage(response, await payloadOf(response)));
        return;
      }
      await refresh();
      setMessage("Đã xác minh thành công.");
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    }
  }

  async function submitQuotation(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch("/api/supplier/session/quotation", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items: summary?.rfq.items.map((item) => ({ request_for_quotation_item: item.name, qty: item.qty, rate: Number(rates[item.name] ?? 0) })) }) });
      if (!response.ok) {
        setMessage(errorMessage(response, await payloadOf(response)));
        return;
      }
      setMessage("Đã submit quotation và khóa quotation.");
      await refresh();
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    }
  }

  async function submitDelivery(event: FormEvent) {
    event.preventDefault();
    try {
      const response = await fetch("/api/supplier/session/delivery", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ delivery_date: deliveryDate, idempotency_key: crypto.randomUUID(), items: (summary?.purchase_order?.items ?? []).map((item) => ({ purchase_order_item: item.name, delivered_qty: Number(deliveryQty[item.name] ?? 0), uom: item.uom })) }) });
      if (!response.ok) {
        setMessage(errorMessage(response, await payloadOf(response)));
        return;
      }
      setMessage("Đã tạo Purchase Receipt thành công.");
      await refresh();
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    }
  }

  async function submitXml(event: FormEvent) {
    event.preventDefault();
    if (!xmlFile) return;
    try {
      const form = new FormData();
      form.set("file", xmlFile);
      form.set("idempotency_key", crypto.randomUUID());
      const response = await fetch("/api/supplier/session/xml-invoice", { method: "POST", body: form });
      if (!response.ok) {
        setMessage(errorMessage(response, await payloadOf(response)));
        return;
      }
      setMessage("Đã tạo Purchase Invoice thành công.");
      setXmlFile(null);
      await refresh();
    } catch {
      setMessage("Không thể kết nối Supplier Portal. Vui lòng thử lại sau.");
    }
  }

  async function logout() {
    await fetch("/api/supplier/session/logout", { method: "POST" }).catch(() => undefined);
    setSummary(null);
    setMessage("Đã đăng xuất.");
  }

  if (!summary) {
    return (
      <main className="mx-auto max-w-lg space-y-6 p-6 md:p-12">
        <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-700">LeTRON Supplier Portal</p><h1 className="mt-3 text-3xl font-bold">Xác minh quotation</h1><p className="mt-2 text-muted-foreground">Không cần đăng nhập. Xác minh bằng OTP gửi tới email đã đăng ký.</p></div>
        <button className="h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground disabled:opacity-50" disabled={!magicId || sendingOtp || otpCooldownSeconds > 0} onClick={() => void requestOtp()}>{sendingOtp ? "Đang gửi OTP…" : otpCooldownSeconds > 0 ? `Gửi lại sau ${otpCooldownSeconds}s` : "Gửi Email OTP"}</button>
        {sent ? <form className="space-y-4 rounded-xl border bg-card p-5" onSubmit={(event) => void verify(event)}><label className="block space-y-2 text-sm font-medium" htmlFor="supplier-otp">Email OTP<input className="h-10 w-full rounded-md border bg-background px-3" id="supplier-otp" inputMode="numeric" maxLength={6} value={otp} onChange={(event) => setOtp(event.target.value)} /></label><button className="h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground" type="submit">Xác minh và vào portal</button></form> : null}
        <p role="status">{message}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6 md:p-12">
      <header className="flex items-start justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-700">LeTRON Supplier Portal</p><h1 className="mt-3 text-3xl font-bold">Supplier workspace</h1><p className="mt-2 text-muted-foreground">Supplier: {summary.supplier}</p></div><button className="rounded-md border px-3 py-2 text-sm" onClick={() => void logout()}>Đăng xuất</button></header>
      <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">Request for Quotation</h2><p className="mt-3 text-sm">RFQ: {summary.rfq.name} · Trạng thái: {summary.rfq.status} · Approval: {summary.approval_status} · Hạn: {summary.deadline_at}</p></section>
      {summary.quotation ? <p className="rounded-md bg-emerald-50 p-4 text-sm text-emerald-800">Quotation đã submit: {summary.quotation.name}. Đã khóa.</p> : <form className="space-y-4 rounded-xl border bg-card p-5" onSubmit={(event) => void submitQuotation(event)}><h2 className="font-semibold">Nhập báo giá</h2>{summary.rfq.items.map((item) => <div className="grid gap-2 sm:grid-cols-[1fr_10rem]" key={item.name}><label className="text-sm">{item.item_code} — {item.description || "Item"}<span className="block text-muted-foreground">Số lượng: {item.qty} {item.uom}</span></label><input className="h-10 rounded-md border bg-background px-3" min="0" step="0.01" required type="number" value={rates[item.name] ?? ""} onChange={(event) => setRates((current) => ({ ...current, [item.name]: event.target.value }))} /></div>)}<button className="h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground" type="submit">Submit quotation</button></form>}
      {summary.purchase_order ? <><section className="space-y-4 rounded-xl border bg-card p-5"><h2 className="font-semibold">Purchase Order: {summary.purchase_order.name}</h2><p className="text-sm">{summary.purchase_order.status} · {summary.purchase_order.currency}</p><form className="space-y-3" onSubmit={(event) => void submitDelivery(event)}><h3 className="font-medium">Delivery confirmation</h3><input className="h-10 rounded-md border bg-background px-3" required type="date" value={deliveryDate} onChange={(event) => setDeliveryDate(event.target.value)} />{summary.purchase_order.items.map((item) => <div className="grid gap-2 sm:grid-cols-[1fr_10rem]" key={item.name}><label className="text-sm">{item.item_code} · đặt {item.qty} {item.uom}</label><input className="h-10 rounded-md border bg-background px-3" min="0" max={item.qty} step="0.01" type="number" value={deliveryQty[item.name] ?? ""} onChange={(event) => setDeliveryQty((current) => ({ ...current, [item.name]: event.target.value }))} /></div>)}<button className="h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground" type="submit">Gửi xác nhận và tạo Receipt</button></form></section><section className="space-y-4 rounded-xl border bg-card p-5"><h2 className="font-semibold">XML Invoice</h2><p className="text-sm text-muted-foreground">Receipt: {summary.purchase_receipt?.[0]?.status ?? "Chưa tạo"} · Payment: {summary.payment_status}</p><form className="flex flex-wrap gap-3" onSubmit={(event) => void submitXml(event)}><input accept=".xml,text/xml,application/xml" required type="file" onChange={(event) => setXmlFile(event.target.files?.[0] ?? null)} /><button className="h-10 rounded-md bg-primary px-4 text-sm text-primary-foreground" type="submit">Upload và tạo Invoice</button></form></section></> : null}
      <p role="status">{message}</p>
    </main>
  );
}
