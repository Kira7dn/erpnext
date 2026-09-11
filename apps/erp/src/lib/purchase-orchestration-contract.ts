import {
  RequestforQuotationWriteSchema,
} from "../generated/zod";

export type OrchestrationRow = Record<string, unknown>;
export type OrchestrationItem = {
  name?: string;
  item_code: string;
  qty: number;
  schedule_date?: string;
  warehouse?: string;
  uom?: string;
  stock_uom?: string;
  conversion_factor?: number;
  rate?: number;
  material_request?: string;
  material_request_item?: string;
};

export function buildRfqPayload(
  materialRequest: OrchestrationRow,
  suppliers: string[],
  items: OrchestrationItem[],
  orchestrationId?: string,
): OrchestrationRow {
  const payload = {
    naming_series: "RFQ-.YYYYMMDD.-.####",
    company: materialRequest.company,
    transaction_date: materialRequest.transaction_date,
    subject: materialRequest.title || "RFQ from Material Request",
    suppliers: suppliers.map((supplier) => ({ supplier })),
    items: items.map(({ name, rate, material_request, ...item }) => {
      void name;
      void rate;
      void material_request;
      return item;
    }),
    ...(orchestrationId ? { custom_letron_orchestration_id: orchestrationId } : {}),
  };
  return RequestforQuotationWriteSchema.parse(payload);
}

export function itemsFromCreatedMaterialRequest(materialRequest: OrchestrationRow): OrchestrationItem[] {
  if (!Array.isArray(materialRequest.items) || !materialRequest.items.length)
    throw new Error("ERP_MATERIAL_REQUEST_ITEMS_MISSING");
  return materialRequest.items.map((item, index) => {
    const source = item as OrchestrationRow;
    const itemCode = String(source.item_code ?? "").trim();
    const qty = Number(source.qty);
    if (!itemCode || !Number.isFinite(qty) || qty <= 0)
      throw new Error(`ERP_MATERIAL_REQUEST_ITEM_INVALID_${index + 1}`);
    return {
      item_code: itemCode,
      qty,
      schedule_date: String(source.schedule_date ?? "").trim() || undefined,
      warehouse: String(source.warehouse ?? "").trim() || undefined,
      uom: String(source.uom ?? "").trim() || undefined,
      stock_uom: String(source.stock_uom ?? source.uom ?? "").trim() || undefined,
      conversion_factor: Number(source.conversion_factor) || 1,
      rate: Number(source.rate ?? source.price_list_rate) || 0,
      name: String(source.name ?? "").trim() || undefined,
      material_request: String(source.material_request ?? materialRequest.name ?? "").trim() || undefined,
      material_request_item: String(source.material_request_item ?? source.name ?? "").trim() || undefined,
    };
  });
}

export async function hydrateRfqItems(
  items: OrchestrationItem[],
  resolveItem: (itemCode: string) => Promise<OrchestrationRow>,
): Promise<OrchestrationItem[]> {
  return Promise.all(items.map(async (item) => {
    if (item.stock_uom && item.uom) return item;
    if (item.uom) return { ...item, stock_uom: item.uom };
    const source = await resolveItem(item.item_code);
    const uom = String(source.stock_uom ?? source.purchase_uom ?? source.uom ?? "").trim();
    return uom ? { ...item, stock_uom: uom, uom } : item;
  }));
}
