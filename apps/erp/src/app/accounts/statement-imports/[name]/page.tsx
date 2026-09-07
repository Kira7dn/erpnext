import { cookies } from "next/headers";
import Link from "next/link";

import { AccountingShell } from "@/components/accounting-shell";
import { StatementDetailsEditor } from "@/components/statement-details-editor";
import { accountingGatewayRequest } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function StatementImportDetailPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const decoded = decodeURIComponent(name);
  let record: Record<string, unknown> | null = null;
  let details: Record<string, unknown> | null = null;
  let error: string | null = null;
  try { const cookieHeader = (await cookies()).toString(); [record, details] = await Promise.all([accountingGatewayRequest<Record<string, unknown>>(`/statement-imports/${encodeURIComponent(decoded)}`, cookieHeader), accountingGatewayRequest<Record<string, unknown>>(`/statement-imports/${encodeURIComponent(decoded)}/details`, cookieHeader)]); } catch (cause) { error = cause instanceof Error ? cause.message : "Không thể tải statement import"; }
  return <AccountingShell><main className="mx-auto max-w-6xl space-y-6 p-5 md:p-8"><div className="flex items-center gap-3"><Link className="text-sm text-primary hover:underline" href="/accounts/statement-imports">← Statement imports</Link><h1 className="text-3xl font-bold">{decoded}</h1></div>{error ? <p className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : <><div className="grid gap-5 lg:grid-cols-2"><Panel title="Import log" value={record} /><Panel title="Statement details" value={details} /></div><StatementDetailsEditor name={decoded} initialDetails={details} /></>}</main></AccountingShell>;
}

function Panel({ title, value }: { title: string; value: Record<string, unknown> | null }) { return <section className="rounded-xl border bg-card p-5"><h2 className="font-semibold">{title}</h2><pre className="mt-4 max-h-[620px] overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(value, null, 2)}</pre></section>; }
