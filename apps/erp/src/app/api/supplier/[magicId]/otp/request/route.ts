import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause } from "@/lib/api-error";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function POST(request: NextRequest, context: { params: Promise<{ magicId: string }> }) {
  const { magicId } = await context.params;
  try {
    const data = await supplierPortalRequest("request_otp", { magic_token: magicId });
    return NextResponse.json({ data });
  } catch (error) { return apiErrorFromCause(error, "otp_request_failed", "OTP could not be requested."); }
}
