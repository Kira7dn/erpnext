import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { ArrowLeft, AlertCircle } from "lucide-react";
import Link from "next/link";

import { AccountingRecordActions } from "@/components/accounting-record-actions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { GatewayAccessDeniedError, GatewayAuthenticationRequiredError, getAccountingResource, isAccountingResource, type AccountingResource } from "@/lib/letron-api";
import { accountingLabel } from "@/lib/ui-labels";
import { larkLoginHref } from "@/lib/auth-navigation";
import { AuthErrorActions } from "@/components/auth-error-actions";

export const dynamic = "force-dynamic";

const title = (resource: AccountingResource) => accountingLabel(resource);

export default async function AccountingResourceDetailPage({ params }: { params: Promise<{ resource: string; name: string }> }) {
  const { resource, name } = await params;
  if (!isAccountingResource(resource)) notFound();
  let record: Record<string, unknown> | null = null;
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;
  try {
    record = await getAccountingResource(resource, decodeURIComponent(name), (await cookies()).toString());
  } catch (cause) {
    needsLogin = cause instanceof GatewayAuthenticationRequiredError;
    accessDenied = cause instanceof GatewayAccessDeniedError;
    error = cause instanceof Error ? cause.message : "Không thể kết nối Letron Gateway.";
  }
  const returnTo = `/accounts/${resource}/${encodeURIComponent(name)}`;
  return <main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div className="flex items-center gap-3"><Button variant="outline" size="sm" asChild><Link href={`/accounts/${resource}`}><ArrowLeft className="mr-2 size-4" />Back</Link></Button><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / {title(resource)}</div><h1 className="mt-1 text-3xl font-bold tracking-tight">{decodeURIComponent(name)}</h1></div></div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập bằng Lark" : accessDenied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu"}</AlertTitle><AlertDescription>{error}{needsLogin ? <AuthErrorActions loginHref={larkLoginHref(returnTo)} /> : null}</AlertDescription></Alert> : <div className="space-y-6"><section className="overflow-hidden rounded-xl border bg-card shadow-sm"><div className="flex flex-col gap-3 border-b p-5 sm:flex-row sm:items-center sm:justify-between"><div><h2 className="font-semibold">{title(resource)} details</h2><p className="text-sm text-muted-foreground">Live record from Letron API.</p></div><Button variant="outline" asChild><Link href={`/accounts/${resource}/${encodeURIComponent(name)}/edit`}>Edit</Link></Button></div><dl className="grid gap-4 p-5 sm:grid-cols-2">{Object.entries(record ?? {}).map(([key, value]) => <div className="rounded-lg border p-4" key={key}><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="mt-2 break-words text-sm">{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</dd></div>)}</dl></section><AccountingRecordActions resource={resource} name={decodeURIComponent(name)} /></div>}</main>;
}
