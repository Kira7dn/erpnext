import { cookies } from "next/headers";
import { gatewayRequest, getStockResource } from "@/lib/letron-api";
import { WarehouseForm } from "@/components/warehouse-form";
export const dynamic = "force-dynamic";
export default async function EditPurchaseWarehousePage({ params }: { params: Promise<{ name: string }> }) { const name = decodeURIComponent((await params).name); const cookie = (await cookies()).toString(); const [initial, warehouses] = await Promise.all([getStockResource("warehouses", name, cookie), gatewayRequest<Record<string, unknown>[]>("/api/v1/stock/warehouses?limit_page_length=100", cookie)]); return <main className="mx-auto max-w-5xl space-y-6 p-5 md:p-8"><div><div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-violet-700">Purchase / PUR-04</div><h1 className="text-3xl font-bold tracking-tight">Sửa Warehouse</h1></div><WarehouseForm initial={initial} warehouses={warehouses} basePath="/purchase" /></main>; }
