import { cookies } from "next/headers";
import { AlertCircle, Plus } from "lucide-react";

import { BankAccountsTable } from "@/components/bank-accounts-table";
import { ResourcePagination } from "@/components/resource-pagination";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  GatewayAccessDeniedError,
  GatewayAuthenticationRequiredError,
  listBankAccounts,
  RESOURCE_PAGE_SIZE,
  resourcePageQuery,
  type BankAccount,
} from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function BankAccountsPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const { page: rawPage } = await searchParams;
  const page = Math.max(1, Number.parseInt(rawPage ?? "1", 10) || 1);
  let accounts: BankAccount[] = [];
  let hasNext = false;
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;

  try {
    accounts = await listBankAccounts((await cookies()).toString(), resourcePageQuery(page));
    hasNext = accounts.length > RESOURCE_PAGE_SIZE;
    accounts = accounts.slice(0, RESOURCE_PAGE_SIZE);
  } catch (cause) {
    needsLogin = cause instanceof GatewayAuthenticationRequiredError;
    accessDenied = cause instanceof GatewayAccessDeniedError;
    error = cause instanceof Error ? cause.message : "Không thể kết nối Letron Gateway.";
  }

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600"><span>LeTRON-Kế toán</span><span>/</span><span>Banking</span></div>
            <h1 className="text-3xl font-bold tracking-tight">Tài khoản ngân hàng</h1>
            <p className="mt-2 text-muted-foreground">Dữ liệu lấy trực tiếp qua LeTRON-Global Portal Gateway.</p>
          </div>
          <Button><Plus className="mr-2 size-4" />Thêm tài khoản ngân hàng</Button>
        </div>
        <div className="flex items-center gap-2"><Badge variant={error ? "destructive" : "default"}>{error ? "Gateway không khả dụng" : "API đã kết nối"}</Badge><span className="text-xs text-muted-foreground">LeTRON-Global Portal SSO · policy enforced</span></div>
        {error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập qua LeTRON-Global Portal" : accessDenied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu từ Letron Gateway"}</AlertTitle><AlertDescription><p>{error}</p>{needsLogin ? <a className="mt-3 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground" href="/api/auth/login">Đăng nhập bằng Lark</a> : null}</AlertDescription></Alert> : <><BankAccountsTable accounts={accounts} />{accounts.length || page > 1 ? <ResourcePagination basePath="/accounts/bank-accounts" page={page} hasNext={hasNext} /> : null}</>}
      </main>
  );
}
