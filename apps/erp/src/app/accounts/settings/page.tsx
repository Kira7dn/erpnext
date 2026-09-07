import { AccountingShell } from "@/components/accounting-shell";
import { AccountsSettings } from "@/components/accounts-settings";

export default function AccountsSettingsPage() { return <AccountingShell><main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Letron ERP / Accounts</div><h1 className="mt-2 text-3xl font-bold tracking-tight">Accounting settings</h1></div><AccountsSettings /></main></AccountingShell>; }
