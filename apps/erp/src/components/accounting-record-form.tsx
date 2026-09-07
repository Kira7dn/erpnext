"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { AccountingFormField, AccountingResource } from "@/lib/letron-api";

function initialValue(field: AccountingFormField, value: unknown): string | boolean {
  if (field.type === "boolean") return Boolean(value);
  if (field.type === "array") return value ? JSON.stringify(value, null, 2) : "[]";
  return value === undefined || value === null ? "" : String(value);
}

export function AccountingRecordForm({ resource, fields, initial, name }: Readonly<{ resource: AccountingResource; fields: AccountingFormField[]; initial?: Record<string, unknown>; name?: string }>) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string | boolean>>(() => Object.fromEntries(fields.map((field) => [field.name, initialValue(field, initial?.[field.name])] )));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  function change(field: AccountingFormField, value: string | boolean) { setValues((current) => ({ ...current, [field.name]: value })); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(null);
    const payload: Record<string, unknown> = {};
    for (const field of fields) {
      const value = values[field.name];
      if (field.required && (value === "" || value === undefined)) { setError(`${field.name} is required`); setSaving(false); return; }
      if (value === "" || value === undefined) continue;
      if (field.type === "boolean") payload[field.name] = value;
      else if (field.type === "number" || field.type === "integer") payload[field.name] = Number(value);
      else if (field.type === "array") { try { payload[field.name] = JSON.parse(String(value)); } catch { setError(`${field.name} must contain valid JSON`); setSaving(false); return; } }
      else payload[field.name] = value;
    }
    const endpoint = `/api/accounting/${resource}${name ? `/${encodeURIComponent(name)}` : ""}`;
    try {
      const response = await fetch(endpoint, { method: name ? "PUT" : "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error((await response.text()).slice(0, 300) || `HTTP ${response.status}`);
      const data = await response.json() as { data?: { name?: string }; message?: { name?: string } };
      const createdName = data.data?.name ?? data.message?.name;
      router.push(createdName ? `/accounts/${resource}/${encodeURIComponent(createdName)}` : `/accounts/${resource}`);
      router.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Save failed"); }
    finally { setSaving(false); }
  }
  return <form className="space-y-6 rounded-xl border bg-card p-5 shadow-sm" onSubmit={submit}><div className="grid gap-5 md:grid-cols-2">{fields.map((field) => <div className={field.type === "array" ? "space-y-2 md:col-span-2" : "space-y-2"} key={field.name}><Label htmlFor={field.name}>{field.name.replaceAll("_", " ")}{field.required ? " *" : ""}</Label>{field.type === "boolean" ? <input className="size-4 accent-blue-600" id={field.name} type="checkbox" checked={Boolean(values[field.name])} onChange={(event) => change(field, event.target.checked)} /> : field.enum?.length ? <select className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" id={field.name} value={String(values[field.name] ?? "")} onChange={(event) => change(field, event.target.value)}><option value="">Select...</option>{field.enum.map((option) => <option key={option} value={option}>{option}</option>)}</select> : field.type === "array" ? <Textarea id={field.name} rows={8} value={String(values[field.name] ?? "")} onChange={(event) => change(field, event.target.value)} /> : <Input id={field.name} type={field.format === "date" ? "date" : field.format === "time" ? "time" : field.type === "number" || field.type === "integer" ? "number" : "text"} value={String(values[field.name] ?? "")} onChange={(event) => change(field, event.target.value)} />}{field.targetDoctype ? <p className="text-xs text-muted-foreground">Link: {field.targetDoctype}</p> : null}</div>)}</div>{error ? <p className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}<Button disabled={saving} type="submit">{saving ? "Saving..." : name ? "Save changes" : "Create record"}</Button></form>;
}
