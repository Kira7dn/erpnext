import type { MetadataRoute } from "next";
import { NextResponse } from "next/server";

export function GET(): NextResponse<MetadataRoute.Manifest> {
  return NextResponse.json({
    id: "/purchase",
    name: "LeTRON-Mua hàng",
    short_name: "LeTRON Mua hàng",
    description: "Phân hệ mua hàng LeTRON",
    start_url: "/purchase",
    scope: "/purchase",
    display: "standalone",
    background_color: "#f8fafc",
    theme_color: "#7c3aed",
    lang: "vi",
    icons: [{ src: "/purchase/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  });
}
