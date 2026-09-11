export type LarkApprovalAutoApproveResponse = {
  status: string;
  taskId?: string;
  idempotent: boolean;
};

export function parseLarkApprovalAutoApproveResponse(value: unknown): LarkApprovalAutoApproveResponse {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("LARK_APPROVAL_AUTO_APPROVE_RESPONSE_INVALID");
  }
  const row = value as Record<string, unknown>;
  if (typeof row.status !== "string" || !row.status.trim() || typeof row.idempotent !== "boolean") {
    throw new Error("LARK_APPROVAL_AUTO_APPROVE_RESPONSE_INVALID");
  }
  if (row.taskId !== undefined && typeof row.taskId !== "string") {
    throw new Error("LARK_APPROVAL_AUTO_APPROVE_RESPONSE_INVALID");
  }
  return {
    status: row.status,
    ...(row.taskId === undefined ? {} : { taskId: row.taskId }),
    idempotent: row.idempotent,
  };
}
