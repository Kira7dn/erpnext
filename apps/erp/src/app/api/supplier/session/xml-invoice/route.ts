import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, apiErrorResponse } from "@/lib/api-error";
import { supplierPortalRequest, supplierPortalUpload } from "@/lib/supplier-portal";
import { getSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function GET(request: Request) {
  const portalSession = await getSupplierPortalSession(request.headers.get("cookie"));
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  try { return NextResponse.json({ data: await supplierPortalRequest("get_submissions", { portal_access_id: portalSession.access.access_id }) }); }
  catch (error) { return apiErrorFromCause(error, "invoice_load_failed", "Invoice submissions could not be loaded."); }
}

export async function POST(request: NextRequest) {
  const portalSession = await getSupplierPortalSession(request.headers.get("cookie"));
  if (!portalSession) return apiErrorResponse("supplier_session_required", 401, "Supplier session is required.");
  const incoming = await request.formData();
  const file = incoming.get("file");
  if (!(file instanceof File)) return apiErrorResponse("xml_file_required", 400, "An XML file is required.");
  const form = new FormData();
  form.set("portal_access_id", portalSession.access.access_id);
  const idempotencyKey = String(incoming.get("idempotency_key") ?? "").trim();
  if (!idempotencyKey) return apiErrorResponse("idempotency_key_required", 400, "idempotency_key is required.");
  form.set("idempotency_key", idempotencyKey);
  form.set("invoice_number", String(incoming.get("invoice_number") ?? ""));
  form.set("invoice_date", String(incoming.get("invoice_date") ?? ""));
  form.set("supplier_tax_id", String(incoming.get("supplier_tax_id") ?? ""));
  form.set("invoice_total", String(incoming.get("invoice_total") ?? ""));
  form.set("file", file);
  try { return NextResponse.json({ data: await supplierPortalUpload("upload_xml_invoice", form) }, { status: 201 }); }
  catch (error) { return apiErrorFromCause(error, "invoice_upload_failed", "Invoice upload could not be completed."); }
}
