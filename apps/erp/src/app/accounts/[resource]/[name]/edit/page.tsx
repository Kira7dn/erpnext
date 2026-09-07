import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import Link from "next/link";

import { AccountingRecordForm } from "@/components/accounting-record-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { GatewayAccessDeniedError, GatewayAuthenticationRequiredError, getAccountingFormFields, getAccountingResource, isAccountingResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function EditAccountingResourcePage({ params }: { params: Promise<{ resource: string; name: string }> }) {
  const { resource, name } = await params;
  if (!isAccountingResource(resource)) notFound();
  const decodedName = decodeURIComponent(name);
  let record: Record<string, unknown> | null = null;
  let error: string | null = null;
  try { record = await getAccountingResource(resource, decodedName, (await cookies()).toString()); } catch (cause) { error = cause instanceof GatewayAuthenticationRequiredError ? "Đăng nhập qua Global Portal để chỉnh sửa." : cause instanceof GatewayAccessDeniedError ? "Tài khoản hiện tại chưa được cấp quyền chỉnh sửa." : cause instanceof Error ? cause.message : "Không thể tải bản ghi."; }
  return <main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div className="flex items-center justify-between"><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / Edit</div><h1 className="mt-1 text-3xl font-bold tracking-tight">{decodedName}</h1></div><Button variant="outline" asChild><Link href={`/accounts/${resource}/${encodeURIComponent(decodedName)}`}>Cancel</Link></Button></div>{error ? <Alert variant="destructive"><AlertTitle>Không thể chỉnh sửa bản ghi</AlertTitle><AlertDescription>{error}<a className="mt-3 block underline" href="/api/auth/login">Đăng nhập qua Global Portal</a></AlertDescription></Alert> : <AccountingRecordForm resource={resource} fields={getAccountingFormFields(resource)} initial={record ?? undefined} name={decodedName} />}</main>;
}
