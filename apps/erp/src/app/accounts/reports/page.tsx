import { AccountingNativeReports } from "@/components/accounting-native-reports";
import { AccountingShell } from "@/components/accounting-shell";

export const dynamic = "force-dynamic";

export default function AccountingReportsPage() { return <AccountingShell><main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">LeTRON-Kế toán / Reports</div><h1 className="text-3xl font-bold tracking-tight">Báo cáo kế toán</h1><p className="mt-2 text-muted-foreground">Báo cáo native ERPNext qua typed Letron API.</p></div><AccountingNativeReports /></main></AccountingShell>; }

