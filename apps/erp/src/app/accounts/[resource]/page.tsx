import { cookies } from "next/headers";
import { AlertCircle } from "lucide-react";
import Link from "next/link";

import { AccountingResourceTable } from "@/components/accounting-resource-table";
import { ResourcePagination } from "@/components/resource-pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ACCOUNTING_RESOURCES, GatewayAccessDeniedError, GatewayAuthenticationRequiredError, isAccountingResource, listAccountingResource, RESOURCE_PAGE_SIZE, resourcePageQuery, type AccountingResource } from "@/lib/letron-api";
import { accountingLabel } from "@/lib/ui-labels";

export const dynamic = "force-dynamic";

const title = (resource: AccountingResource) => accountingLabel(resource);

export function generateStaticParams() {
  return ACCOUNTING_RESOURCES.filter((resource) => resource !== "bank-accounts").map((resource) => ({ resource }));
}

export default async function AccountingResourcePage({ params, searchParams }: { params: Promise<{ resource: string }>; searchParams: Promise<{ page?: string }> }) {
  const { resource } = await params;
  if (!isAccountingResource(resource) || resource === "bank-accounts") return null;
  const { page: rawPage } = await searchParams;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);
  let rows: Record<string, unknown>[] = [];
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;
  let hasNext = false;
  try {
    rows = await listAccountingResource(resource, (await cookies()).toString(), resourcePageQuery(page));
    hasNext = rows.length > RESOURCE_PAGE_SIZE;
    rows = rows.slice(0, RESOURCE_PAGE_SIZE);
  } catch (cause) {
    needsLogin = cause instanceof GatewayAuthenticationRequiredError;
    accessDenied = cause instanceof GatewayAccessDeniedError;
    error = cause instanceof Error ? cause.message : "Không thể kết nối Letron Gateway.";
  }
  return <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / API resource</div><h1 className="text-3xl font-bold tracking-tight">{title(resource)}</h1><p className="mt-2 text-muted-foreground">Dữ liệu lấy trực tiếp qua Letron Global Portal Gateway.</p></div><Button asChild><Link href={`/accounts/${resource}/new`}>New record</Link></Button></div>{error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập qua Global Portal" : accessDenied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu"}</AlertTitle><AlertDescription>{error}{needsLogin ? <a className="mt-3 block underline" href="/api/auth/login">Đăng nhập qua Global Portal</a> : null}</AlertDescription></Alert> : <><AccountingResourceTable resource={resource} rows={rows} />{rows.length || page > 1 ? <ResourcePagination basePath={`/accounts/${resource}`} page={page} hasNext={hasNext} /> : null}</>}</main>;
}
