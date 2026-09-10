import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause, ApiRequestError } from "@/lib/api-error";
import { sendSupplierPortalMail, supplierPortalRequest, type SupplierPortalMail } from "@/lib/supplier-portal";

export async function POST(request: NextRequest, context: { params: Promise<{ magicId: string }> }) {
  const { magicId } = await context.params;
  try {
    const data = await supplierPortalRequest<{ status: string; expires_in_seconds: number; resend_after_seconds: number; mail: SupplierPortalMail }>("request_otp", { magic_token: magicId });
    if (!data.mail) throw new ApiRequestError("lark_mail_payload_missing", "OTP email payload is missing.", 502, true);
    await sendSupplierPortalMail(data.mail);
    const publicData = { status: data.status, expires_in_seconds: data.expires_in_seconds, resend_after_seconds: data.resend_after_seconds };
    return NextResponse.json({ data: publicData });
  } catch (error) { return apiErrorFromCause(error, "otp_request_failed", "OTP could not be requested."); }
}
