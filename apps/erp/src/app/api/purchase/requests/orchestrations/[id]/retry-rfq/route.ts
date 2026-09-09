import { NextResponse } from "next/server";
import { requestAuthCredential } from "@/lib/request-auth";
import {
  orchestrationHttpStatus,
  retryPurchaseRfqById,
} from "@/lib/purchase-orchestration";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const cookieHeader = await requestAuthCredential(request);
  if (!cookieHeader)
    return NextResponse.json(
      { error: "authentication_required" },
      { status: 401 },
    );
  const { id } = await context.params;
  try {
    const state = await retryPurchaseRfqById(cookieHeader, id);
    return NextResponse.json({ data: state, message: state.status });
  } catch (cause) {
    const state = (cause as { orchestration?: unknown }).orchestration;
    if (state)
      return NextResponse.json({ data: state, message: "partial_failure" });
    return NextResponse.json(
      { error: cause instanceof Error ? cause.message : "RFQ retry failed." },
      { status: orchestrationHttpStatus(cause) },
    );
  }
}
