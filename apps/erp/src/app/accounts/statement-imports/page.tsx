import { StatementImporter } from "@/components/statement-importer";

export const dynamic = "force-dynamic";

export default function StatementImportsPage() {
  return <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-blue-600">Accounting / Banking</div><h1 className="text-3xl font-bold tracking-tight">Statement importer</h1><p className="mt-2 text-muted-foreground">Quản lý Bank Statement Import Log và chuẩn bị dữ liệu CSV/PDF cho reconciliation.</p></div><StatementImporter /></main>;
}
