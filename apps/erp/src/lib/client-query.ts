"use client";

import { ErpQueryError } from "@/components/query-provider";
import { publicErrorMessage, type RemoteErrorPayload } from "@/lib/error-contract";

type ApiPayload<T> = { data?: T; message?: T | string } & RemoteErrorPayload;

export async function clientQuery<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({})) as ApiPayload<T>;
  if (!response.ok) {
    const code = typeof payload.error === "string" && /^[a-z0-9_]+$/.test(payload.error)
      ? payload.error
      : `http_${response.status}`;
    const message = publicErrorMessage(payload.error, response.status);
    const retryable = typeof (payload as { retryable?: unknown }).retryable === "boolean"
      ? Boolean((payload as { retryable: boolean }).retryable)
      : response.status >= 500;
    throw new ErpQueryError(response.status, message, code, retryable);
  }
  return (payload.data ?? payload.message) as T;
}
