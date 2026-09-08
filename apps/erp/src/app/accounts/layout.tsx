import type { Metadata } from "next";
import { AccountingAppShell } from "@/components/accounting-shell";

export const metadata: Metadata = {
  title: "LeTRON-Kế toán",
  description: "Phân hệ Accounting của LeTRON",
  manifest: "/accounts/manifest.webmanifest",
};

export default function AccountingLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AccountingAppShell>{children}</AccountingAppShell>;
}
