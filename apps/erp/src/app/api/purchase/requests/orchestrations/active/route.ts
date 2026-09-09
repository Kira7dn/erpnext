import { NextRequest, NextResponse } from "next/server";
import { getActivePurchaseOrchestrations } from "@/lib/purchase-orchestration";
import { requestAuthCredential } from "@/lib/request-auth";

export async function GET(request: NextRequest) {
  const cookieHeader = await requestAuthCredential(request);
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
