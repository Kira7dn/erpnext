"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Archive, BarChart3, BookOpen, Box, Building2, ClipboardList, Cog, CreditCard, FileBarChart, FileText, Landmark, MapPin, ReceiptText, Settings, Upload, Users, WalletCards, Wrench } from "lucide-react";

const icons = { Archive, BarChart3, BookOpen, Box, Building2, ClipboardList, Cog, CreditCard, FileBarChart, FileText, Landmark, MapPin, ReceiptText, Settings, Upload, Users, WalletCards, Wrench } as const;
type SidebarItem = readonly [label: string, href: string, icon: keyof typeof icons];

export function AppSidebarNav({
  items,
  tone,
  label,
}: Readonly<{ items: readonly SidebarItem[]; tone: "blue" | "emerald"; label: string }>) {
  const pathname = usePathname() ?? "/";
  const palette = tone === "blue"
    ? { active: "bg-blue-600 text-white shadow-sm", idle: "text-slate-400 hover:bg-slate-900 hover:text-white", focus: "focus-visible:ring-blue-400" }
    : { active: "bg-emerald-600 text-white shadow-sm", idle: "text-emerald-200 hover:bg-emerald-900 hover:text-white", focus: "focus-visible:ring-emerald-400" };

  return <nav className="space-y-1" aria-label={label}>
    {items.map(([itemLabel, href, iconName]) => {
      const Icon = icons[iconName];
      const isRoot = href === "/accounts" || href === "/assets" || href === "/purchase";
      const active = isRoot ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
      return <Link
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${active ? palette.active : palette.idle} ${palette.focus}`}
        data-active={active ? "true" : "false"}
        href={href}
        key={href}
        prefetch={false}
      ><Icon aria-hidden="true" className="size-4" />{itemLabel}</Link>;
    })}
  </nav>;
}
