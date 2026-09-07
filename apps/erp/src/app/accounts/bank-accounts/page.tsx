import { cookies } from "next/headers";
import { AlertCircle, Plus } from "lucide-react";

import { AccountingShell } from "@/components/accounting-shell";
import { BankAccountsTable } from "@/components/bank-accounts-table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  GatewayAccessDeniedError,
  GatewayAuthenticationRequiredError,
  listBankAccounts,
  type BankAccount,
} from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function BankAccountsPage() {
  let accounts: BankAccount[] = [];
  let error: string | null = null;
  let needsLogin = false;
  let accessDenied = false;

  try {
    accounts = await listBankAccounts((await cookies()).toString());
  } catch (cause) {
    needsLogin = cause instanceof GatewayAuthenticationRequiredError;
    accessDenied = cause instanceof GatewayAccessDeniedError;
    error = cause instanceof Error ? cause.message : "Không thể kết nối Letron Gateway.";
  }

  return (
    <AccountingShell>
      <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600"><span>Accounting</span><span>/</span><span>Banking</span></div>
            <h1 className="text-3xl font-bold tracking-tight">Bank accounts</h1>
            <p className="mt-2 text-muted-foreground">Tài khoản ngân hàng lấy trực tiếp qua Global Portal Gateway.</p>
          </div>
          <Button><Plus className="mr-2 size-4" />New bank account</Button>
        </div>
        <div className="flex items-center gap-2"><Badge variant={error ? "destructive" : "default"}>{error ? "Gateway unavailable" : "API connected"}</Badge><span className="text-xs text-muted-foreground">Global Portal SSO · policy enforced</span></div>
        {error ? <Alert variant="destructive"><AlertCircle className="size-4" /><AlertTitle>{needsLogin ? "Đăng nhập qua Global Portal" : accessDenied ? "Chưa được cấp quyền" : "Không lấy được dữ liệu từ Letron Gateway"}</AlertTitle><AlertDescription><p>{error}</p>{needsLogin ? <a className="mt-3 inline-flex rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground" href="/api/auth/login">Đăng nhập bằng Lark</a> : null}</AlertDescription></Alert> : <BankAccountsTable accounts={accounts} />}
      </main>
    </AccountingShell>
  );
}
