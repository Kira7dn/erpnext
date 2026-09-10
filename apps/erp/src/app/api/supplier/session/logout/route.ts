import { NextResponse } from "next/server";
import { clearSupplierPortalSession } from "@/lib/supplier-portal-session";

export async function POST() {
  await clearSupplierPortalSession();
  return NextResponse.json({ status: "logged_out" });
}
