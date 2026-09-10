export type RemoteErrorPayload = {
  error?: unknown;
  retryable?: unknown;
  retry_after_seconds?: unknown;
};

export function validErrorCode(value: unknown): string | undefined {
  return typeof value === "string" && /^[a-z][a-z0-9_]*$/.test(value) ? value : undefined;
}

export function retryAfterSeconds(value: unknown): number | undefined {
  const seconds = typeof value === "number" ? value : Number(value);
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : undefined;
}

const USER_FACING_MESSAGES: Record<string, string> = {
  supplier_otp_rate_limited: "Bạn vừa yêu cầu OTP. Vui lòng thử lại khi bộ đếm kết thúc.",
  supplier_portal_rate_limited: "Bạn vừa thao tác quá nhanh. Vui lòng thử lại sau.",
  supplier_portal_not_found: "Magic Link không hợp lệ hoặc đã hết hạn.",
  supplier_portal_access_denied: "Magic Link không hợp lệ hoặc đã hết hạn.",
  supplier_portal_authentication_required: "Phiên Supplier Portal không hợp lệ.",
  supplier_portal_unavailable: "Supplier Portal đang tạm thời không khả dụng.",
  supplier_session_required: "Phiên Supplier Portal đã hết hạn. Vui lòng mở lại Magic Link.",
};

export function publicErrorMessage(code: unknown, status: number): string {
  const validCode = validErrorCode(code);
  if (validCode && USER_FACING_MESSAGES[validCode]) return USER_FACING_MESSAGES[validCode];
  if (status === 401) return "Yêu cầu xác thực không hợp lệ.";
  if (status === 403) return "Bạn không có quyền thực hiện thao tác này.";
  if (status === 404) return "Không tìm thấy tài nguyên yêu cầu.";
  if (status === 429) return "Bạn vừa thao tác quá nhanh. Vui lòng thử lại sau.";
  if (status >= 500) return "Dịch vụ đang tạm thời không khả dụng.";
  return "Yêu cầu không hợp lệ.";
}
