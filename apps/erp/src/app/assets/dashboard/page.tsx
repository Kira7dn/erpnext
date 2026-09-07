import { cookies } from "next/headers";
import { AlertCircle, Archive, CheckCircle2, FileClock, Trash2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { assetsGatewayRequest } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function AssetsDashboardPage() {
  let dashboard: { counts?: Record<string, number> } | null = null;
  let error: string | null = null;
  try { dashboard = await assetsGatewayRequest<{ counts?: Record<string, number> }>("dashboard", (await cookies()).toString()); }
  catch (cause) { error = cause instanceof Error ? cause.message : "Không thể tải dashboard tài sản"; }
  const counts = dashboard?.counts ?? {};
  const cards = [["Tổng tài sản", counts.total ?? 0, Archive], ["Đang sử dụng", counts.active ?? 0, CheckCircle2], ["Bản nháp", counts.draft ?? 0, FileClock], ["Đã thanh lý", counts.scrapped ?? 0, Trash2]] as const;
  return <main className="mx-auto max-w-7xl space-y-8 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Assets / Dashboard</div><h1 className="text-3xl font-bold tracking-tight">Asset dashboard</h1><p className="mt-2 text-muted-foreground">Các chỉ số được đọc trực tiếp từ ERPNext.</p></div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>Không lấy được dữ liệu</AlertTitle><AlertDescription>{error}</AlertDescription></Alert> : <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{cards.map(([label, value, Icon]) => <div className="rounded-xl border bg-card p-5 shadow-sm" key={label}><Icon className="size-5 text-emerald-700" /><p className="mt-5 text-sm text-muted-foreground">{label}</p><p className="mt-1 text-3xl font-bold">{value}</p></div>)}</div>}</main>;
}
