import type { Metadata } from "next";
import { AssetsAppShell } from "@/components/assets-shell";

export const metadata: Metadata = {
  title: "LeTRON-Tài sản",
  description: "Phân hệ Assets của LeTRON",
};

export default function AssetsLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AssetsAppShell>{children}</AssetsAppShell>;
}
