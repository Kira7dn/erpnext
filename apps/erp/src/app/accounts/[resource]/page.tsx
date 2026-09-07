import { cookies } from "next/headers";
import { AlertCircle } from "lucide-react";
import Link from "next/link";

import { AccountingResourceTable } from "@/components/accounting-resource-table";
import { AccountingShell } from "@/components/accounting-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ACCOUNTING_RESOURCES, GatewayAccessDeniedError, GatewayAuthenticationRequiredError, isAccountingResource, listAccountingResource, type AccountingResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

const title = (resource: AccountingResource) => resource.split("-").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");

export function generateStaticParams() {
  return ACCOUNTING_RESOURCES.filter((resource) => resource !== "bank-accounts").map((resource) => ({ resource }));
}

export default async function AccountingResourcePage({ params }: { params: Promise<{ resource: string }> }) {
  const { resource } = await params;
  if (!isAccountingResource(resource) || resource === "bank-accounts") return null;
  let rows: Record<string, unknown>[] = [];
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;
  try {
    rows = await listAccountingResource(resource, (await cookies()).toString());
  } catch (cause) {
    needsLogin = cause instanceof GatewayAuthenticationRequiredError;
    accessDenied = cause instanceof GatewayAccessDeniedError;
    error = cause instanceof Error ? cause.message : "Không thể kết nối Letron Gateway.";
  }
  return <AccountingShell><main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / API resource</div><h1 className="text-3xl font-bold tracking-tight">{title(resource)}</h1><p className="mt-2 text-muted-foreground">Dữ liệu lấy trực tiếp qua Letron Global Portal Gateway.</p></div><Button asChild><Link href={`/accounts/${resource}/new`}>New record</Link></Button></div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập qua Global Portal" : accessDenied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu"}</AlertTitle><AlertDescription>{error}{needsLogin ? <a className="mt-3 block underline" href="/api/auth/login">Đăng nhập bằng Lark</a> : null}</AlertDescription></Alert> : <AccountingResourceTable resource={resource} rows={rows} />}</main></AccountingShell>;
}
