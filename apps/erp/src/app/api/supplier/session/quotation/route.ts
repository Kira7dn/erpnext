import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { openSupplierApproval, supplierPortalRequest } from "@/lib/supplier-portal";
import { createPurchaseOrderDraft } from "@/lib/supplier-portal-core";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function POST(request: NextRequest) {
  const portalSession = await getSupplierPortalSession();
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  let claimedProcess = "";
  let approvalCreated = false;
  try {
    const result = await supplierPortalRequest("submit_quotation", { portal_access_id: portalSession.access.access_id, ...(body ?? {}) });
    const process = await supplierPortalRequest<{ process: string }>("get_process_summary", { portal_access_id: portalSession.access.access_id });
    const gate = await supplierPortalRequest<{ process: string; ready: boolean; selected_supplier_quotation?: string; orchestration_id: string }>("evaluate_approval_gate", { orchestration_id: process.process });
    const claim = gate.ready && gate.selected_supplier_quotation
      ? await supplierPortalRequest<{ claimed: boolean }>("claim_approval_opening", { process: gate.process })
      : null;
    claimedProcess = claim?.claimed ? gate.process : "";
    const po = claim?.claimed && gate.selected_supplier_quotation
      ? await createPurchaseOrderDraft(gate.process, gate.selected_supplier_quotation)
      : null;
    const approval = claim?.claimed && po?.name
      ? await openSupplierApproval({
          orchestration_id: gate.orchestration_id,
          selected_supplier_quotation_name: gate.selected_supplier_quotation ?? "",
          erp_purchase_order_name: String(po.name),
          justification: `Tự động chọn báo giá có tổng giá thấp nhất: ${gate.selected_supplier_quotation}.`,
        })
      : null;
    if (approval && typeof approval === "object") {
      const approvalId = String((approval as { instanceCode?: unknown; instance_code?: unknown }).instanceCode ?? (approval as { instance_code?: unknown }).instance_code ?? "");
      if (approvalId) {
        approvalCreated = true;
        await supplierPortalRequest("mark_approval_opened", { process: gate.process, approval_id: approvalId });
      }
    }
    return NextResponse.json({ data: { result, gate, approval } });
  } catch (error) {
    if (claimedProcess && !approvalCreated) {
      await supplierPortalRequest("release_approval_opening", { process: claimedProcess }).catch((releaseError) => {
        console.error("[supplier-portal] approval opening release failed", releaseError instanceof Error ? releaseError.message : releaseError);
      });
    }
    console.error("[supplier-portal] quotation submit failed", error instanceof Error ? error.message : error);
    return apiErrorFromCause(error, "quotation_submit_failed", "Quotation could not be submitted.");
  }
}
