import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LeTRON-Tài sản",
  description: "Phân hệ Assets của LeTRON",
};

export default function AssetsLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
