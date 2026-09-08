import type { MetadataRoute } from "next";
import { NextResponse } from "next/server";

export function GET(): NextResponse<MetadataRoute.Manifest> {
  return NextResponse.json({
    id: "/accounts",
    name: "LeTRON-Kế toán",
    short_name: "LeTRON Kế toán",
    description: "Phân hệ kế toán LeTRON",
    start_url: "/accounts",
    scope: "/accounts",
    display: "standalone",
    background_color: "#f8fafc",
    theme_color: "#1d4ed8",
    lang: "vi",
    icons: [{ src: "/accounts/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  });
}
