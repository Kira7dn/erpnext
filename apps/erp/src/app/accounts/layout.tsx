import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LeTRON-Kế toán",
  description: "Phân hệ Accounting của LeTRON",
};

export default function AccountingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
