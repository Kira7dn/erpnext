import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { supplierPortalRequest } from "@/lib/supplier-portal";

const COOKIE = "letron_supplier_session";
const COOKIE_PATH = "/api/supplier";

export async function POST() {
  const jar = await cookies();
  const session = jar.get(COOKIE)?.value;
  if (session) await supplierPortalRequest("logout_session", { session_token: session }).catch(() => undefined);
  jar.set(COOKIE, "", { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", maxAge: 0, path: COOKIE_PATH });
  return NextResponse.json({ status: "logged_out" });
}
