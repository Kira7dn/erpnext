import Link from "next/link";
import { CircleUserRound } from "lucide-react";
import { getPortalUser } from "@/lib/portal-session";
import { larkLoginHref } from "@/lib/auth-navigation";

export async function UserSessionStatus({ returnTo }: { returnTo: string }) {
  const user = await getPortalUser();
  if (!user) {
    return <Link className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted" href={larkLoginHref(returnTo)}><span className="size-2 rounded-full bg-slate-400" />Chưa đăng nhập</Link>;
  }
  return <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs" title={user.email}><CircleUserRound className="size-4 text-emerald-600" /><span className="hidden max-w-40 truncate font-medium sm:inline">{user.displayName}</span><span className="size-2 rounded-full bg-emerald-500" title="Đã đăng nhập" /></div>;
}
