export type RemoteErrorPayload = {
  error?: unknown;
  message?: unknown;
  _server_messages?: unknown;
};

export function parseFrappeMessage(value: unknown): string | undefined {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    const message = (value as { message?: unknown }).message;
    return typeof message === "string" && message.trim() ? message.trim() : undefined;
  }
  if (typeof value !== "string") return undefined;
  try {
    const parsed = JSON.parse(value) as unknown;
    const rows = Array.isArray(parsed) ? parsed : [parsed];
    for (const row of rows) {
      if (typeof row === "string") {
        const nested = parseFrappeMessage(row);
        if (nested) return nested;
      }
      if (row && typeof row === "object" && typeof (row as { message?: unknown }).message === "string")
        return (row as { message: string }).message;
    }
  } catch {
    return undefined;
  }
  return undefined;
}

export function remoteErrorMessage(
  payload: RemoteErrorPayload,
  fallback: string,
): string {
  const frappeMessage = parseFrappeMessage(payload._server_messages);
  if (frappeMessage) return frappeMessage.slice(0, 500);
  const message = parseFrappeMessage(payload.message);
  if (message) return message.slice(0, 500);
  if (typeof payload.message === "string" && payload.message.trim())
    return payload.message.trim().slice(0, 500);
  return fallback;
}
