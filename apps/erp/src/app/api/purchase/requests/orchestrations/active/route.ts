import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { getActivePurchaseOrchestrations } from "@/lib/purchase-orchestration";

export async function GET() {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader)
    return NextResponse.json(
      { error: "authentication_required" },
      { status: 401 },
    );
  try {
    return NextResponse.json({
      data: await getActivePurchaseOrchestrations(cookieHeader),
    });
  } catch {
    return NextResponse.json({ error: "orchestration_unavailable" }, { status: 503 });
  }
}
