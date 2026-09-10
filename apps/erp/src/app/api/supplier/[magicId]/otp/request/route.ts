import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause } from "@/lib/api-error";
import { sendSupplierPortalMail } from "@/lib/supplier-portal";
import { buildOtpMail, requestNextOtp } from "@/lib/supplier-portal-session";

export async function POST(request: NextRequest, context: { params: Promise<{ magicId: string }> }) {
  const { magicId } = await context.params;
  try {
    const data = await requestNextOtp(magicId);
    const delivery = await sendSupplierPortalMail(buildOtpMail(data.access, data.otp));
    const publicData = { status: "sent", expires_in_seconds: 300, resend_after_seconds: 15, mail_delivery: { message_id: delivery.messageId, idempotent: delivery.idempotent } };
    return NextResponse.json({ data: publicData });
  } catch (error) { return apiErrorFromCause(error, "otp_request_failed", "OTP could not be requested."); }
}
