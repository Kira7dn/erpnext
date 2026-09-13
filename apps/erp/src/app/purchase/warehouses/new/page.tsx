import { cookies } from "next/headers";
import { gatewayRequest } from "@/lib/letron-api";
import { WarehouseForm } from "@/components/warehouse-form";
export const dynamic = "force-dynamic";
export default async function NewPurchaseWarehousePage() { const warehouses = await gatewayRequest<Record<string, unknown>[]>("/api/v1/stock/warehouses?limit_page_length=100", (await cookies()).toString()); return <main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Purchase / PUR-04</div><h1 className="text-3xl font-bold tracking-tight">Tạo Warehouse</h1></div><WarehouseForm warehouses={warehouses} basePath="/purchase" /></main>; }
