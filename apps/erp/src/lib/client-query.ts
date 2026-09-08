"use client";

import { ErpQueryError } from "@/components/query-provider";

type ApiPayload<T> = { data?: T; message?: T | string; exc_type?: string };

export async function clientQuery<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });
  const payload = await response.json().catch(() => ({})) as ApiPayload<T>;
  if (!response.ok) {
    const message = typeof payload.message === "string" ? payload.message : payload.exc_type ?? `HTTP ${response.status}`;
    throw new ErpQueryError(response.status, message);
  }
  return (payload.data ?? payload.message) as T;
}
