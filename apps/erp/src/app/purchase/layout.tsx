import type { Metadata } from "next";
import { PurchaseShell } from "@/components/purchase-shell";

export const metadata: Metadata = {
  title: "LeTRON-Mua hàng",
  description: "Phân hệ Purchase của LeTRON",
  manifest: "/purchase/manifest.webmanifest",
};

export default function PurchaseLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <PurchaseShell>{children}</PurchaseShell>; }
