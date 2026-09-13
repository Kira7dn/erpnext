import { cookies } from "next/headers";
import { WarehouseForm } from "@/components/warehouse-form";
import { listStockResource } from "@/lib/letron-api";
export const dynamic = "force-dynamic";
export default async function NewWarehousePage() { const rows = await listStockResource("warehouses", (await cookies()).toString(), "limit_page_length=100"); return <main className="mx-auto max-w-4xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Stock / WH-01</div><h1 className="text-3xl font-bold tracking-tight">Tạo Warehouse</h1></div><WarehouseForm warehouses={rows} /></main>; }
