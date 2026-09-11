import { NextResponse } from "next/server";
import { publicErrorMessage, retryAfterSeconds, validErrorCode } from "./error-contract";
import type { RemoteErrorPayload } from "./error-contract";

export { publicErrorMessage } from "./error-contract";
export type { RemoteErrorPayload } from "./error-contract";

export type ApiErrorBody = {
  error: string;
  message: string;
  retryable: boolean;
  stage?: string;
  retry_after_seconds?: number;
};

export type ApiErrorCode = string;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;
  readonly retryAfterSeconds?: number;

  constructor(code: ApiErrorCode, message: string, status: number, retryable = status >= 500, retryAfterSecondsValue?: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.retryable = retryable;
    this.retryAfterSeconds = retryAfterSecondsValue;
  }
}

export function apiErrorResponse(
  code: string,
  status: number,
  message: string,
  retryable = status >= 500,
  retryAfterSecondsValue?: number,
  stage?: string,
): NextResponse<ApiErrorBody> {
  const body: ApiErrorBody = { error: validErrorCode(code) ?? "request_failed", message, retryable };
  if (stage) body.stage = stage;
  if (retryAfterSecondsValue !== undefined) body.retry_after_seconds = retryAfterSecondsValue;
  const headers = retryAfterSecondsValue !== undefined ? { "Retry-After": String(retryAfterSecondsValue) } : undefined;
  return NextResponse.json(body, { status, headers });
}

export async function apiErrorFromResponse(
  response: Response,
  rejectedCode: string,
): Promise<NextResponse<ApiErrorBody>> {
  const payload = (await response.json().catch(() => ({}))) as RemoteErrorPayload & {
    retryable?: unknown;
  };
  const code = validErrorCode(payload.error) ?? rejectedCode;
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : response.status === 429 || response.status >= 500;
  const retryAfter = retryAfterSeconds(payload.retry_after_seconds) ?? retryAfterSeconds(response.headers.get("Retry-After"));
  return apiErrorResponse(
    code,
    response.status,
    publicErrorMessage(code, response.status),
    retryable,
    retryAfter,
  );
}

export function apiErrorFromCause(
  cause: unknown,
  errorCode: ApiErrorCode,
  errorMessage: string,
  errorStatus = 400,
  stage?: string,
): NextResponse<ApiErrorBody> {
  if (cause instanceof ApiRequestError)
    return apiErrorResponse(cause.code, cause.status, cause.message, cause.retryable, cause.retryAfterSeconds, stage);
  return apiErrorResponse(errorCode, errorStatus, errorMessage, errorStatus >= 500, undefined, stage);
}
