import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function GET() {
  const sessionToken = (await cookies()).get("letron_supplier_session")?.value;
  if (!sessionToken) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try {
    return NextResponse.json({ data: await supplierPortalRequest("get_process_summary", { session_token: sessionToken }) });
  } catch (error) { return apiErrorFromCause(error, "supplier_session_invalid", "Supplier session is invalid.", 401); }
}
