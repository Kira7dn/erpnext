"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { AssetResource } from "@/lib/letron-api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clientQuery } from "@/lib/client-query";

const SUBMITTABLE = new Set<AssetResource>(["assets", "asset-capitalizations", "asset-movements", "asset-repairs", "asset-value-adjustments"]);

export function AssetLifecycleActions({ resource, name, docstatus }: Readonly<{ resource: AssetResource; name: string; docstatus?: unknown }>) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const submitted = Number(docstatus) === 1;
  const mutation = useMutation({ mutationFn: (action: "submit" | "cancel") => clientQuery(`/api/assets/${resource}/${encodeURIComponent(name)}/${action}`, { method: "POST" }), onSuccess: async (_, action) => { await queryClient.invalidateQueries({ queryKey: ["asset-record", resource, name] }); await queryClient.invalidateQueries({ queryKey: ["assets", resource] }); setMessage(`${action} completed.`); router.refresh(); } });
  if (!SUBMITTABLE.has(resource)) return null;
  async function run(action: "submit" | "cancel") { setBusy(action); setMessage(null); try { await mutation.mutateAsync(action); } catch (cause) { setMessage(cause instanceof Error ? cause.message : `${action} failed`); } finally { setBusy(null); } }
  return <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-5 shadow-sm"><div className="mr-auto"><h2 className="font-semibold">Vòng đời chứng từ</h2><p className="text-sm text-muted-foreground">Thao tác native Submit/Cancel của ERPNext.</p></div>{submitted ? <Button disabled={busy !== null} onClick={() => run("cancel")} variant="outline" type="button">{busy === "cancel" ? "Đang hủy..." : "Cancel chứng từ"}</Button> : <Button disabled={busy !== null} onClick={() => run("submit")} type="button">{busy === "submit" ? "Đang submit..." : "Submit chứng từ"}</Button>}{message ? <p className="basis-full text-sm text-muted-foreground">{message}</p> : null}</div>;
}
