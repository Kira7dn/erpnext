import { AccountingShell } from "@/components/accounting-shell";
import { BankReconciliationWorkbench } from "@/components/accounting-interactive";
import { BankReconciliationActions } from "@/components/bank-reconciliation-actions";

export const dynamic = "force-dynamic";

export default function BankReconciliationPage() {
  return <AccountingShell><main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / Banking</div><h1 className="text-3xl font-bold tracking-tight">Bank reconciliation</h1><p className="mt-2 text-muted-foreground">Lọc giao dịch, xem payment liên kết và xử lý clearance qua Letron Gateway.</p></div><BankReconciliationWorkbench /><BankReconciliationActions /></main></AccountingShell>;
}
