import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { getPurchaseOrchestrationById } from "@/lib/purchase-orchestration";

type Context = { params: Promise<{ id: string }> };

export async function GET(_request: NextRequest, context: Context) {
  const cookieHeader = (await cookies()).toString();
  if (!cookieHeader)
    return NextResponse.json(
      { error: "authentication_required" },
      { status: 401 },
    );
  const { id } = await context.params;
  const state = await getPurchaseOrchestrationById(cookieHeader, id);
  return state
    ? NextResponse.json({ data: state })
    : NextResponse.json({ error: "orchestration_not_found" }, { status: 404 });
}
