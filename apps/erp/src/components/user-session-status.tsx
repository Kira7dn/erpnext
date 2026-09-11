import { CircleUserRound } from "lucide-react";
import { getPortalUser } from "@/lib/portal-session";
import { larkLoginHref } from "@/lib/auth-navigation";
import type { AppKey } from "@/lib/erp-auth-session";

export async function UserSessionStatus({ returnTo }: { returnTo: string }) {
  const appKey: AppKey = returnTo.startsWith("/assets") ? "assets" : returnTo.startsWith("/purchase") ? "purchase" : "accounts";
  const user = await getPortalUser(appKey);
  if (!user) {
    return (
      <a
        className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted"
        href={larkLoginHref(returnTo)}
        target="_top"
        rel="noopener"
      >
        <span className="size-2 rounded-full bg-slate-400" />
        Chưa đăng nhập
      </a>
    );
  }
  return (
    <div
      className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs"
      title={user.email || user.displayName}
    >
      <CircleUserRound className="size-4 text-emerald-600" />
      <span className="hidden max-w-40 truncate font-medium sm:inline">
        {user.displayName}
      </span>
      <span
        className="size-2 rounded-full bg-emerald-500"
        title="Đã đăng nhập"
      />
    </div>
  );
}
