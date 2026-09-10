import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function GET() {
  const session = (await cookies()).get("letron_supplier_session")?.value;
  if (!session) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("get_purchase_order", { session_token: session }) }); }
  catch (error) { return apiErrorFromCause(error, "po_load_failed", "Purchase Order could not be loaded.", 404); }
}
