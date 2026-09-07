import { notFound } from "next/navigation";
import Link from "next/link";

import { AccountingRecordForm } from "@/components/accounting-record-form";
import { AccountingShell } from "@/components/accounting-shell";
import { Button } from "@/components/ui/button";
import { getAccountingFormFields, isAccountingResource } from "@/lib/letron-api";

export const dynamic = "force-dynamic";

export default async function NewAccountingResourcePage({ params }: { params: Promise<{ resource: string }> }) {
  const { resource } = await params;
  if (!isAccountingResource(resource)) notFound();
  return <AccountingShell><main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div className="flex items-center justify-between"><div><div className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / New</div><h1 className="mt-1 text-3xl font-bold tracking-tight">Create {resource.replaceAll("-", " ")}</h1></div><Button variant="outline" asChild><Link href={`/accounts/${resource}`}>Cancel</Link></Button></div><AccountingRecordForm resource={resource} fields={getAccountingFormFields(resource)} /></main></AccountingShell>;
}
