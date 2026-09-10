import { NextRequest, NextResponse } from "next/server";
import { apiErrorFromCause } from "@/lib/api-error";
import { verifyNextOtp } from "@/lib/supplier-portal-session";

const COOKIE = "letron_supplier_session";
const COOKIE_PATH = "/api/supplier";

export async function POST(request: NextRequest, context: { params: Promise<{ magicId: string }> }) {
  const { magicId } = await context.params;
  const body = (await request.json().catch(() => null)) as { otp?: unknown } | null;
  try {
    const data = await verifyNextOtp(magicId, String(body?.otp ?? ""));
    const response = NextResponse.json({ data: { status: "verified" } });
    response.cookies.set(COOKIE, data.sessionToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      maxAge: data.expiresInSeconds,
      path: COOKIE_PATH,
    });
    return response;
  } catch (error) { return apiErrorFromCause(error, "otp_invalid_or_expired", "OTP is invalid or expired", 401); }
}
