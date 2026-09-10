import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { openSupplierApproval, supplierPortalRequest } from "@/lib/supplier-portal";

export async function POST(request: NextRequest) {
  const sessionToken = (await cookies()).get("letron_supplier_session")?.value;
  if (!sessionToken) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  try {
    const result = await supplierPortalRequest("submit_quotation", { session_token: sessionToken, ...(body ?? {}) });
    const process = await supplierPortalRequest<{ material_request: string }>("get_process_summary", { session_token: sessionToken });
    const gate = await supplierPortalRequest<{ process: string; ready: boolean; selected_supplier_quotation?: string; orchestration_id: string }>("evaluate_approval_gate", { material_request: process.material_request });
    const claim = gate.ready && gate.selected_supplier_quotation
      ? await supplierPortalRequest<{ claimed: boolean }>("claim_approval_opening", { process: gate.process })
      : null;
    const approval = claim?.claimed
      ? await openSupplierApproval({
          orchestration_id: gate.orchestration_id,
          selected_supplier_quotation_name: gate.selected_supplier_quotation ?? "",
          justification: `Tự động chọn báo giá có tổng giá thấp nhất: ${gate.selected_supplier_quotation}.`,
        })
      : null;
    if (approval && typeof approval === "object") {
      const approvalId = String((approval as { instanceCode?: unknown; instance_code?: unknown }).instanceCode ?? (approval as { instance_code?: unknown }).instance_code ?? "");
      if (approvalId) {
        const session = (await cookies()).get("letron_supplier_session")?.value;
        if (session) await supplierPortalRequest("mark_approval_opened", { process: gate.process, approval_id: approvalId });
      }
    }
    return NextResponse.json({ data: { result, gate, approval } });
  } catch (error) {
    console.error("[supplier-portal] quotation submit failed", error instanceof Error ? error.message : error);
    return apiErrorFromCause(error, "quotation_submit_failed", "Quotation could not be submitted.");
  }
}
