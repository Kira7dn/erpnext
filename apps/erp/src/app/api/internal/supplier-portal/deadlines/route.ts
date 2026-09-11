import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse, ApiRequestError } from "@/lib/api-error";
import { openSupplierApproval, supplierPortalCronRequest, supplierPortalRequest } from "@/lib/supplier-portal";
import { createPurchaseOrderDraft } from "@/lib/supplier-portal-core";

export async function POST(request: NextRequest) {
  const supplied = request.headers.get("x-letron-cron-secret") ?? "";
  if (!supplied || supplied !== process.env.LETRON_INTERNAL_API_SECRET) {
    return apiErrorResponse("forbidden", 403, "Internal access is required.");
  }
  try {
    const gate = await supplierPortalCronRequest<{
      evaluated: number;
      ready: Array<{
        process: string;
        orchestration_id: string;
        selected_supplier_quotation: string;
        submitted_count: number;
      }>;
    }>();
    const opened = [];
    for (const item of gate.ready ?? []) {
      const claim = await supplierPortalRequest<{ claimed: boolean }>("claim_approval_opening", { process: item.process });
      if (!claim.claimed) continue;
      let approvalCreated = false;
      try {
        const po = await createPurchaseOrderDraft(item.process, item.selected_supplier_quotation);
        const approval = await openSupplierApproval({
          orchestration_id: item.orchestration_id,
          selected_supplier_quotation_name: item.selected_supplier_quotation,
          erp_purchase_order_name: String(po.name ?? ""),
          justification: `Tự động chọn báo giá ${item.selected_supplier_quotation} có tổng giá thấp nhất trong ${item.submitted_count} báo giá đã nhận; mở sau thời hạn 3 ngày của Material Request.`,
        });
        const approvalId = String((approval as { instanceCode?: unknown; instance_code?: unknown }).instanceCode ?? (approval as { instance_code?: unknown }).instance_code ?? "").trim();
        if (!approvalId)
          throw new ApiRequestError("approval_instance_missing", "Supplier approval instance was not created.", 502);
        approvalCreated = true;
        const marked = await supplierPortalRequest("mark_approval_opened", {
          process: item.process,
          approval_id: approvalId,
        });
        opened.push({ process: item.process, approval_id: approvalId, marked });
      } catch (cause) {
        if (!approvalCreated) {
          await supplierPortalRequest("release_approval_opening", { process: item.process }).catch((releaseError) => {
            console.error("[supplier-portal] deadline approval release failed", releaseError instanceof Error ? releaseError.message : releaseError);
          });
        }
        throw cause;
      }
    }
    return NextResponse.json({ data: gate, opened });
  } catch (cause) {
    return apiErrorFromCause(cause, "deadline_evaluation_failed", "Deadline evaluation failed.", 502);
  }
}
