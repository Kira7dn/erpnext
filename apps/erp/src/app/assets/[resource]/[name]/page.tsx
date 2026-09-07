import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AssetsShell } from "@/components/assets-shell";
import { AssetActionPanel } from "@/components/asset-action-panel";
import { AssetLifecycleActions } from "@/components/asset-lifecycle-actions";
import { AssetRecordForm } from "@/components/asset-record-form";
import { Button } from "@/components/ui/button";
import { getAssetFormFields, assetsGatewayRequest, isAssetResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function AssetDetailPage({ params }: { params: Promise<{ resource: string; name: string }> }) {
  const { resource, name } = await params;
  if (!isAssetResource(resource)) notFound();
  const decoded = decodeURIComponent(name);
  let record: Record<string, unknown> | null = null;
  let error: string | null = null;
  try { record = await assetsGatewayRequest<Record<string, unknown>>(`${resource}/${encodeURIComponent(decoded)}`, (await cookies()).toString()); }
  catch (cause) { error = cause instanceof Error ? cause.message : "Không thể tải tài sản"; }
  return <AssetsShell><main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div className="flex items-center gap-3"><Button variant="outline" size="sm" asChild><Link href={`/assets/${resource}`}>Back</Link></Button><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Assets / {resource}</div><h1 className="mt-1 text-3xl font-bold">{decoded}</h1></div></div>{error ? <p className="rounded-md bg-destructive/10 p-4 text-sm text-destructive">{error}</p> : <><section className="rounded-xl border bg-card p-5"><dl className="grid gap-4 sm:grid-cols-2">{Object.entries(record ?? {}).map(([key, value]) => <div className="rounded-lg border p-4" key={key}><dt className="text-xs font-semibold uppercase text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="mt-2 break-words text-sm">{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</dd></div>)}</dl></section><AssetLifecycleActions resource={resource} name={decoded} docstatus={record?.docstatus} /><AssetRecordForm resource={resource} fields={getAssetFormFields(resource)} initial={record ?? undefined} name={decoded} />{resource === "assets" ? <AssetActionPanel assetName={decoded} /> : null}</>}</main></AssetsShell>;
}
