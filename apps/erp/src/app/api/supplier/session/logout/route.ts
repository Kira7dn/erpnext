import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { supplierPortalRequest } from "@/lib/supplier-portal";

export async function POST() {
  const jar = await cookies();
  const session = jar.get("letron_supplier_session")?.value;
  if (session) await supplierPortalRequest("logout_session", { session_token: session }).catch(() => undefined);
  jar.delete("letron_supplier_session");
  return NextResponse.json({ status: "logged_out" });
}
