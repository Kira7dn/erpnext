import Link from "next/link";
import { cookies } from "next/headers";
import { StockTable } from "@/components/stock-table";
import { ResourcePagination } from "@/components/resource-pagination";
import { Button } from "@/components/ui/button";
import { listStockResource, RESOURCE_PAGE_SIZE } from "@/lib/letron-api";
export const dynamic = "force-dynamic";
export default async function ReceiptsPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) { const page = Math.max(1, Number.parseInt((await searchParams).page ?? "1", 10) || 1); const rows = await listStockResource("purchase-receipts", (await cookies()).toString(), new URLSearchParams({ limit_page_length: String(RESOURCE_PAGE_SIZE + 1), limit_start: String((page - 1) * RESOURCE_PAGE_SIZE) }).toString()); const hasNext = rows.length > RESOURCE_PAGE_SIZE; return <main className="mx-auto max-w-7xl space-y-6 p-5 md:p-8"><div className="flex items-end justify-between"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Stock / WH-02</div><h1 className="text-3xl font-bold tracking-tight">Purchase Receipt</h1><p className="mt-2 text-muted-foreground">Tiếp nhận hàng từ Purchase Order đã Submit.</p></div><Button asChild><Link href="/stock/receipts/new">Tạo Receipt</Link></Button></div><StockTable resource="purchase-receipts" rows={rows.slice(0, RESOURCE_PAGE_SIZE)} /><ResourcePagination basePath="/stock/receipts" page={page} hasNext={hasNext} tone="emerald" /></main>; }
