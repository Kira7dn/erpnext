import { cookies } from "next/headers";
import Link from "next/link";
import { AlertCircle, FileBarChart } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ASSET_REPORTS, assetsGatewayRequest, GatewayAccessDeniedError, GatewayAuthenticationRequiredError, type AssetReportKey } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

function label(value: string) { const labels: Record<string, string> = { "fixed-asset-register": "Sổ đăng ký tài sản", "asset-depreciation-ledger": "Sổ khấu hao tài sản", "asset-depreciations-and-balances": "Khấu hao và số dư tài sản", "asset-maintenance": "Báo cáo bảo trì tài sản", "asset-activity": "Hoạt động tài sản" }; return labels[value] ?? value; }

export default async function AssetsReportsPage({ searchParams }: { searchParams: Promise<{ report?: string }> }) {
  const selected = (await searchParams).report;
  const report = ASSET_REPORTS.includes(selected as AssetReportKey) ? selected as AssetReportKey : ASSET_REPORTS[0];
  let result: Record<string, unknown> | null = null;
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;
  try { result = await assetsGatewayRequest<Record<string, unknown>>(`reports/report?report_key=${encodeURIComponent(report)}`, (await cookies()).toString()); }
  catch (cause) { needsLogin = cause instanceof GatewayAuthenticationRequiredError; accessDenied = cause instanceof GatewayAccessDeniedError; error = cause instanceof Error ? cause.message : "Không thể chạy báo cáo tài sản"; }
  const rows = Array.isArray(result?.result) ? result.result as Record<string, unknown>[] : Array.isArray(result) ? result as unknown as Record<string, unknown>[] : [];
  return <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Assets / Reports</div><h1 className="text-3xl font-bold tracking-tight">Asset reports</h1><p className="mt-2 text-muted-foreground">Báo cáo native từ Query Report của ERPNext.</p></div><div className="flex flex-wrap gap-2">{ASSET_REPORTS.map((key) => <Button asChild key={key} variant={key === report ? "default" : "outline"}><Link href={`/assets/reports?report=${key}`}>{label(key)}</Link></Button>)}</div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập qua Global Portal" : accessDenied ? "Chưa được cấp quyền" : "Không chạy được báo cáo"}</AlertTitle><AlertDescription><p>{error}</p>{needsLogin ? <a className="mt-3 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground" href="/api/auth/login">Đăng nhập bằng Lark</a> : null}</AlertDescription></Alert> : <section className="overflow-hidden rounded-xl border bg-card shadow-sm"><div className="flex items-center gap-2 border-b p-4 font-semibold"><FileBarChart className="size-4 text-emerald-700" />{label(report)}</div>{rows.length ? <div className="overflow-auto"><table className="w-full text-left text-sm"><thead className="bg-muted/50"><tr>{Object.keys(rows[0]).map((key) => <th className="whitespace-nowrap px-4 py-3 font-semibold" key={key}>{key.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr className="border-t" key={index}>{Object.keys(rows[0]).map((key) => <td className="whitespace-nowrap px-4 py-3" key={key}>{typeof row[key] === "object" ? JSON.stringify(row[key]) : String(row[key] ?? "—")}</td>)}</tr>)}</tbody></table></div> : <p className="p-6 text-sm text-muted-foreground">Báo cáo không trả về dòng dữ liệu.</p>}</section>}</main>;
}
