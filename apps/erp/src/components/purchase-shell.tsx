import { Suspense } from "react";

import { AppSidebarNav } from "@/components/app-sidebar-nav";
import { UserSessionStatus } from "@/components/user-session-status";

const links = [["Tổng quan", "/purchase", "Archive"], ["Nhà cung cấp", "/purchase/suppliers", "Building2"], ["Vật tư / Item", "/purchase/items", "Box"], ["Material Request", "/purchase/requests", "ClipboardList"]] as const;

export function PurchaseShell({ children }: Readonly<{ children: React.ReactNode }>) {
  return <div className="flex min-h-screen bg-muted/30"><aside className="hidden w-64 shrink-0 border-r bg-slate-950 text-slate-300 md:block"><div className="flex h-16 items-center gap-3 border-b border-slate-800 px-5 text-sm font-bold tracking-[0.18em] text-white"><span className="grid size-8 place-items-center rounded-lg bg-violet-600 tracking-normal">L</span>LeTRON</div><div className="px-4 py-6"><p className="mb-3 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-violet-400">LeTRON-Mua hàng</p><AppSidebarNav items={links} label="Điều hướng mua hàng" tone="blue" /></div><div className="absolute bottom-0 w-64 border-t border-slate-800 px-6 py-4 text-xs text-slate-500"><span className="block">Letron Purchase</span><form action="/api/auth/logout?return_to=%2Fpurchase" method="post"><button className="mt-2 underline" type="submit">Đăng xuất</button></form></div></aside><div className="min-w-0 flex-1"><header className="flex h-16 items-center justify-between border-b bg-background px-5 md:px-8"><span className="text-sm font-semibold">LeTRON-Mua hàng</span><div className="flex items-center gap-3"><span className="hidden rounded-full bg-violet-50 px-3 py-1.5 text-xs text-violet-700 sm:inline">Purchase workspace</span><Suspense fallback={<span className="h-8 w-24 animate-pulse rounded-full bg-muted" />}><UserSessionStatus returnTo="/purchase" /></Suspense></div></header>{children}</div></div>;
}
