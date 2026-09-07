import Link from "next/link";
import { ArrowRight, BarChart3, BookOpen, Building2, CreditCard, FileText, ReceiptText, Settings, WalletCards } from "lucide-react";

import { AccountingShell } from "@/components/accounting-shell";
import { ACCOUNTING_RESOURCES, type AccountingResource } from "@/lib/letron-api";

const icons = { banks: Building2, "bank-accounts": WalletCards, "bank-transactions": BarChart3, "bank-transaction-rules": Settings, "cost-centers": BookOpen, "journal-entries": FileText, "modes-of-payment": CreditCard, "payment-entries": CreditCard, "payment-orders": ReceiptText, "payment-requests": ReceiptText, "purchase-invoices": ReceiptText, "sales-invoices": ReceiptText } satisfies Record<AccountingResource, typeof Building2>;
const label = (resource: string) => resource.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

export default function AccountsOverviewPage() {
  return <AccountingShell><main className="mx-auto max-w-7xl space-y-8 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Letron ERP / Accounting</div><h1 className="text-3xl font-bold tracking-tight">Accounting workspace</h1><p className="mt-2 text-muted-foreground">Quản lý chứng từ và dữ liệu kế toán qua Letron API Gateway.</p></div><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{ACCOUNTING_RESOURCES.map((resource) => { const Icon = icons[resource]; return <Link className="group rounded-xl border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md" href={`/accounts/${resource}`} key={resource}><div className="flex items-start justify-between"><span className="grid size-10 place-items-center rounded-lg bg-blue-50 text-blue-700"><Icon className="size-5" /></span><ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-1" /></div><h2 className="mt-5 font-semibold">{label(resource)}</h2><p className="mt-1 text-sm text-muted-foreground">Open live records and details.</p></Link>; })}</div></main></AccountingShell>;
}
