"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClientAuthRecovery } from "@/components/client-auth-recovery";
import { clientQuery, isAuthenticationError } from "@/lib/client-query";

type Settings = Record<string, unknown>;
const settingsKey = ["accounts-settings"] as const;

export function AccountsSettings() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: settingsKey,
    queryFn: () => clientQuery<Settings>("/api/accounting/settings"),
  });
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? JSON.stringify(settings.data ?? {}, null, 2);
  const save = useMutation({
    mutationFn: () =>
      clientQuery<Settings>("/api/accounting/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: value,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKey, data);
      setDraft(JSON.stringify(data, null, 2));
    },
  });
  const error = settings.error ?? save.error;
  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div>
        <h2 className="font-semibold">Accounts Settings</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Đọc và cập nhật cấu hình native từ ERPNext. Các field hệ thống được
          backend bảo vệ.
        </p>
      </div>
      <textarea
        className="min-h-[32rem] w-full rounded-md border bg-background p-3 font-mono text-xs"
        value={value}
        onChange={(event) => setDraft(event.target.value)}
        disabled={settings.isPending}
      />
      {error ? (
        <div className="rounded-md bg-destructive/10 p-3 text-sm">
          <p>
            {error instanceof Error
              ? error.message
              : "Không thể tải Accounts Settings"}
          </p>
          {isAuthenticationError(error) ? <ClientAuthRecovery /> : null}
        </div>
      ) : null}
      {save.isSuccess ? (
        <p className="text-sm text-green-700">Đã lưu Accounts Settings.</p>
      ) : null}
      <button
        className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
        disabled={save.isPending || settings.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Đang lưu…" : "Save settings"}
      </button>
    </section>
  );
}
