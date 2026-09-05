import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getEnv } from "../src/server/env";
import { visiblePolicyFeatures } from "../src/server/access-policy";
import { getPublishedPolicy } from "../src/server/published-policy";
import { getUserBySessionToken, SESSION_COOKIE } from "../src/server/session";

export const dynamic = "force-dynamic";

const featureLabels: Record<string, string> = {
  workspace: "Không gian ERP",
  finance: "Tài chính",
  purchasing: "Mua hàng",
  inventory: "Kho",
  sales: "Bán hàng",
};

function AppIcon({ admin = false }: { admin?: boolean }) {
  return <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-200" aria-hidden="true"><svg className="h-6 w-6 fill-none stroke-current stroke-2" viewBox="0 0 24 24">{admin ? <><path d="M12 3 5 6v5c0 4.2 2.8 7.8 7 9.5 4.2-1.7 7-5.3 7-9.5V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></> : <><path d="M4 5.5 12 2l8 3.5v6.8c0 4.4-3.2 8.2-8 9.7-4.8-1.5-8-5.3-8-9.7V5.5Z" /><path d="M8.2 8.2h7.6M8.2 12h7.6M8.2 15.8h4.5" /></>}</svg></span>;
}

function ApplicationCard({ href, title, description, footer, features, admin = false }: { href: string; title: string; description: string; footer: string; features: string[]; admin?: boolean }) {
  return <a className="group flex min-h-[290px] flex-col rounded-3xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:border-blue-300 hover:shadow-xl hover:shadow-blue-100" href={href}><div className="flex items-start justify-between gap-4"><AppIcon admin={admin} /><span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700"><i className="h-2 w-2 rounded-full bg-emerald-500" />{admin ? "Quản trị" : "Sẵn sàng"}</span></div><div className="mt-6 flex-1"><h3 className="text-xl font-bold text-slate-950">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{description}</p><ul className="mt-4 flex flex-wrap gap-2" aria-label={`Các chức năng của ${title}`}>{features.map((feature) => <li className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600" key={feature}>{feature}</li>)}</ul></div><div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4 text-xs font-semibold text-slate-500"><span>{footer}</span><span className="text-xl text-blue-600 transition group-hover:translate-x-1" aria-hidden="true">→</span></div></a>;
}

export default async function HomePage() {
  const user = await getUserBySessionToken((await cookies()).get(SESSION_COOKIE)?.value);
  if (!user) redirect("/api/auth/lark/start?return_to=/");
  const env = getEnv();
  const published = await getPublishedPolicy();
  const isAccessAdmin = Boolean(env.GLOBAL_ACCESS_ADMIN_GROUP_ID && user.groupIds.includes(env.GLOBAL_ACCESS_ADMIN_GROUP_ID));
  const policyFeatures = published ? visiblePolicyFeatures(published.policy, user.groupIds) : [];
  const canAccessErp = Boolean(published && user.groupIds.includes(published.policy.requiredAccessGroupId));
  const erpFeatures = policyFeatures.filter((id) => id !== "workspace").map((id) => featureLabels[id] ?? id);
  const erpBaseUrl = env.LETRON_SSO_ERP_BASE_URL ?? "http://localhost:8080";
  const erpUrl = `${erpBaseUrl}/api/method/letron_api.sso.launch`;
  const initials = user.displayName.split(/\s+/).filter(Boolean).slice(-2).map((part) => part[0]?.toUpperCase()).join("") || "L";
  const applicationCount = Number(canAccessErp) + Number(isAccessAdmin);

  return <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,_#dbeafe,_transparent_35%),linear-gradient(135deg,_#f8fafc_0%,_#eef2ff_100%)] px-4 py-8 text-slate-900 sm:px-8 lg:py-12"><div className="mx-auto max-w-6xl"><header className="flex flex-col gap-5 border-b border-slate-200/80 pb-8 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 text-xl font-black text-white shadow-lg">L</span><span><strong className="block text-sm font-black tracking-[0.2em] text-slate-950">LETRON</strong><small className="block text-[10px] font-bold tracking-[0.18em] text-blue-600">GLOBAL PORTAL</small></span></div><div className="flex items-center gap-3 rounded-2xl border border-white/80 bg-white/75 px-3 py-2 shadow-sm backdrop-blur" title={user.email}><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100 font-bold text-blue-700">{initials}</span><span className="min-w-0"><strong className="block truncate text-sm text-slate-900">{user.displayName}</strong><small className="block max-w-[220px] truncate text-xs text-slate-500">{user.email}</small></span></div></header><section className="py-12 sm:py-16"><p className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">Không gian làm việc Letron</p><h1 className="mt-4 max-w-3xl text-4xl font-black tracking-tight text-slate-950 sm:text-6xl">Chào mừng trở lại, {user.displayName}</h1><p className="mt-5 max-w-2xl text-base leading-7 text-slate-500 sm:text-lg">Truy cập các hệ thống nội bộ bằng một phiên đăng nhập Lark duy nhất.</p></section><section aria-labelledby="applications-title"><div className="mb-6 flex items-end justify-between gap-4"><div><h2 id="applications-title" className="text-2xl font-bold text-slate-950">Ứng dụng</h2><p className="mt-1 text-sm text-slate-500">Các công cụ được cấp cho tài khoản của bạn.</p></div><span className="rounded-full bg-white px-4 py-2 text-sm font-bold text-slate-600 shadow-sm">{applicationCount} ứng dụng</span></div><div className="grid gap-5 md:grid-cols-2">{canAccessErp ? <ApplicationCard href={erpUrl} title="Letron ERP" description="Những phân hệ hiển thị dưới đây được xác định từ Lark User Group của bạn." footer="SSO qua Lark" features={erpFeatures} /> : null}{isAccessAdmin ? <ApplicationCard href="/admin/access-policy" title="Role Permission Setting" description="Quản lý tập trung role và quyền truy cập ERP theo Lark User Group." footer="Global Access Admin" features={["Access Policy", "CRUD permissions"]} admin /> : null}{!canAccessErp && !isAccessAdmin ? <div className="col-span-full rounded-3xl border border-dashed border-slate-300 bg-white/70 p-12 text-center" role="status"><span className="text-4xl text-slate-300" aria-hidden="true">○</span><h3 className="mt-4 text-lg font-bold text-slate-800">Chưa có ứng dụng được cấp</h3><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">Tài khoản của bạn chưa thuộc User Group có quyền sử dụng ứng dụng Letron.</p></div> : null}</div></section><footer className="mt-16 flex flex-col gap-3 border-t border-slate-200/80 pt-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between"><span>Letron Group · Internal systems</span><form action="/api/auth/logout" method="post"><button className="font-semibold text-slate-600 underline-offset-4 hover:text-blue-600 hover:underline" type="submit">Đăng xuất</button></form></footer></div></main>;
}
