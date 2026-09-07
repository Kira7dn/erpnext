"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const ACTIONS = ["make-asset-movement", "make-journal-entry", "get-manual-depreciation-entries", "has-active-capitalization", "get-asset-depreciation-schedule", "get-asset-item-details", "create-asset-maintenance", "create-asset-repair", "create-asset-capitalization", "get-capitalization-items", "get-capitalization-target-item", "get-capitalization-target-asset", "get-consumed-stock-item-details", "get-consumed-asset-details", "get-service-item-details", "get-warehouse-details", "make-sales-invoice", "split-asset", "create-value-adjustment", "get-asset-value-after-depreciation", "get-accounting-dimensions", "get-maintenance-log", "calculate-next-due-date", "get-repair-downtime", "get-unallocated-repair-cost", "scrap-asset", "restore-asset", "make-depreciation-entry"] as const;

export function AssetActionPanel({ assetName }: Readonly<{ assetName: string }>) {
  const router = useRouter();
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("make-asset-movement");
  const [payload, setPayload] = useState(JSON.stringify({ asset: assetName }, null, 2));
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setMessage(null);
    try {
      const response = await fetch(`/api/assets/actions/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message ?? body.exc_type ?? `HTTP ${response.status}`);
      setMessage("Action completed successfully."); router.refresh();
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Action failed"); }
    finally { setSaving(false); }
  }
  return <form className="space-y-4 rounded-xl border bg-card p-5 shadow-sm" onSubmit={submit}><div><h2 className="font-semibold">Native asset actions</h2><p className="mt-1 text-sm text-muted-foreground">Chỉ các action đã allowlist trong Letron API mới được gọi.</p></div><div className="space-y-2"><Label htmlFor="asset-action">Action</Label><select className="flex h-10 w-full rounded-md border bg-background px-3 text-sm" id="asset-action" value={action} onChange={(event) => setAction(event.target.value as (typeof ACTIONS)[number])}>{ACTIONS.map((item) => <option key={item} value={item}>{item.replaceAll("-", " ")}</option>)}</select></div><div className="space-y-2"><Label htmlFor="asset-action-payload">Payload JSON</Label><Textarea id="asset-action-payload" rows={7} value={payload} onChange={(event) => setPayload(event.target.value)} /></div>{message ? <p className="rounded-md bg-muted p-3 text-sm">{message}</p> : null}<Button disabled={saving} type="submit">{saving ? "Running..." : "Run native action"}</Button></form>;
}
