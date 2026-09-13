import type { Metadata } from "next";
import { StockShell } from "@/components/stock-shell";

export const metadata: Metadata = { title: "LeTRON-Kho", description: "Quản lý kho và phiếu nhập hàng" };
export default function StockLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <StockShell>{children}</StockShell>; }
