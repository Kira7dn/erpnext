import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/assets",
    name: "LeTRON-Tài sản",
    short_name: "LeTRON Tài sản",
    description: "Phân hệ tài sản LeTRON",
    start_url: "/assets",
    scope: "/assets",
    display: "standalone",
    background_color: "#f8fafc",
    theme_color: "#047857",
    lang: "vi",
    icons: [{ src: "/assets/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
