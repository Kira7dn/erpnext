import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function GET() {
  const session = (await cookies()).get("letron_supplier_session")?.value;
  if (!session) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("get_submissions", { session_token: session }) }); }
  catch (error) { return apiErrorFromCause(error, "delivery_load_failed", "Delivery submissions could not be loaded."); }
}

export async function POST(request: NextRequest) {
  const session = (await cookies()).get("letron_supplier_session")?.value;
  if (!session) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("create_delivery_confirmation", { session_token: session, ...(await request.json()) }) }, { status: 201 }); }
  catch (error) { return apiErrorFromCause(error, "delivery_submit_failed", "Delivery confirmation could not be submitted."); }
}
