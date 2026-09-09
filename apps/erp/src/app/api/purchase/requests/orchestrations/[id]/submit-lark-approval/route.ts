import { NextRequest, NextResponse } from "next/server";
import { requestAuthCredential } from "@/lib/request-auth";

import {
  orchestrationHttpStatus,
  submitLarkApprovalById,
  PurchaseOrchestrationValidationError,
} from "@/lib/purchase-orchestration";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return NextResponse.json(
      { error: "authentication_required" },
      { status: 401 },
    );
  const body = (await request.json().catch(() => null)) as {
    supplier_quotation_name?: unknown;
    justification?: unknown;
  } | null;
  const supplierQuotationName = String(body?.supplier_quotation_name ?? "").trim();
  if (!supplierQuotationName)
    return NextResponse.json(
      { error: "supplier_quotation_name_required" },
      { status: 400 },
    );
  const { id } = await context.params;
  try {
    const state = await submitLarkApprovalById(
      cookieHeader,
      id,
      supplierQuotationName,
      String(body?.justification ?? ""),
    );
    return NextResponse.json({ data: state, message: "PENDING" });
  } catch (cause) {
    const state = (cause as { orchestration?: unknown }).orchestration;
    if (state)
      return NextResponse.json({ data: state, message: "approval_failed" });
    return NextResponse.json(
      {
        error:
          cause instanceof PurchaseOrchestrationValidationError || cause instanceof Error
            ? cause.message
            : "Lark approval submission failed.",
      },
      { status: orchestrationHttpStatus(cause) },
    );
  }
}
