"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import type { AccountingResource } from "@/lib/letron-api";
import { clientQuery } from "@/lib/client-query";

const actions: Partial<Record<AccountingResource, string[]>> = { "bank-transactions": ["submit", "cancel", "reconcile", "unreconcile"], "bank-transaction-rules": ["run-evaluation"], "journal-entries": ["submit", "cancel"], "payment-entries": ["submit", "cancel"], "payment-orders": ["submit", "cancel"], "payment-requests": ["submit", "cancel"], "purchase-invoices": ["submit", "cancel"], "sales-invoices": ["submit", "cancel"] };

export function AccountingRecordActions({ resource, name }: Readonly<{ resource: AccountingResource; name: string }>) {
  const router = useRouter(); const queryClient = useQueryClient(); const [busy, setBusy] = useState<string | null>(null); const available = actions[resource] ?? [];
  const mutation = useMutation({ mutationFn: (action: string) => clientQuery(`/api/accounting/${resource}/${encodeURIComponent(name)}/${action}`, { method: "POST" }), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["accounting-record", resource, name] }); await queryClient.invalidateQueries({ queryKey: ["accounts", resource] }); router.refresh(); } });
  if (!available.length) return null;
  async function run(action: string) { if (!window.confirm(`Thực hiện ${action} trên ${name}?`)) return; setBusy(action); try { await mutation.mutateAsync(action); } catch (cause) { window.alert(cause instanceof Error ? cause.message : "Thao tác thất bại"); } finally { setBusy(null); } }
  return <div className="flex flex-wrap gap-2">{available.map((action) => <Button key={action} disabled={busy !== null} variant={action === "cancel" || action === "unreconcile" ? "outline" : "default"} onClick={() => void run(action)}>{busy === action ? "Đang xử lý..." : action === "submit" ? "Submit" : action === "cancel" ? "Cancel" : action}</Button>)}</div>;
}
