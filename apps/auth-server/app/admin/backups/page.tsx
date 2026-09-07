import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";

import { BackupCard } from "../../../src/components/backup-card";
import { getEnv } from "../../../src/server/env";
import { getUserBySessionToken, SESSION_COOKIE } from "../../../src/server/session";

export const dynamic = "force-dynamic";

export default async function BackupsPage() {
  const user = await getUserBySessionToken((await cookies()).get(SESSION_COOKIE)?.value);
  const adminGroupId = getEnv().GLOBAL_ACCESS_ADMIN_GROUP_ID;
  if (!user || !adminGroupId || !user.groupIds.includes(adminGroupId)) redirect("/");

       return <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900 sm:px-8"><div className="mx-auto max-w-6xl"><header className="mb-8 flex items-center justify-between gap-4"><div><p className="text-xs font-black uppercase tracking-[0.18em] text-blue-600">LeTRON-Global Portal / Admin</p><h1 className="mt-2 text-3xl font-black tracking-tight">Sao lưu & Khôi phục</h1><p className="mt-2 text-sm text-slate-500">Quản lý backup ERPNext và thực hiện Restore Drill từ S3.</p></div><Link className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100" href="/">Về Global Portal</Link></header><BackupCard /></div></main>;
}
