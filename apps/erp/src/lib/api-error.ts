import { NextResponse } from "next/server";
import { remoteErrorMessage } from "./error-contract";
import type { RemoteErrorPayload } from "./error-contract";

export { parseFrappeMessage, remoteErrorMessage } from "./error-contract";
export type { RemoteErrorPayload } from "./error-contract";

export type ApiErrorBody = {
  error: string;
  message: string;
  retryable: boolean;
};

export type ApiErrorCode = string;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(code: ApiErrorCode, message: string, status: number, retryable = status >= 500) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
  }
}

export function apiErrorResponse(
  code: string,
  status: number,
  message: string,
  retryable = status >= 500,
): NextResponse<ApiErrorBody> {
  return NextResponse.json({ error: code, message, retryable }, { status });
}

export async function apiErrorFromResponse(
  response: Response,
  fallbackCode: string,
  fallbackMessage: string,
): Promise<NextResponse<ApiErrorBody>> {
  const payload = (await response.json().catch(() => ({}))) as RemoteErrorPayload & {
    retryable?: unknown;
  };
  const code = typeof payload.error === "string" && /^[a-z][a-z0-9_]*$/.test(payload.error)
    ? payload.error
    : fallbackCode;
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : response.status === 429 || response.status >= 500;
  return apiErrorResponse(
    code,
    response.status,
    remoteErrorMessage(payload, fallbackMessage),
    retryable,
  );
}

export function apiErrorFromCause(
  cause: unknown,
  fallbackCode: ApiErrorCode,
  fallbackMessage: string,
  fallbackStatus = 400,
): NextResponse<ApiErrorBody> {
  if (cause instanceof ApiRequestError)
    return apiErrorResponse(cause.code, cause.status, cause.message, cause.retryable);
  return apiErrorResponse(fallbackCode, fallbackStatus, fallbackMessage, fallbackStatus >= 500);
}
