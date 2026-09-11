/**
 * Types for POST /api/v1/stock/purchase-receipts.
 * Source: contracts/generated/openapi/modules/stock.yaml,
 * operationId=createPurchaseReceipt.
 *
 * The generated schema is also used for persisted responses and therefore
 * incorrectly marks Frappe's generated `name` as required for create input.
 * This input type models the actual create operation and keeps response-only
 * fields out of the request contract.
 */
export type PurchaseReceiptItemCreate = {
  item_code: string;
  item_name?: string;
  qty: number;
  uom: string;
  rate: number;
  warehouse: string;
  conversion_factor: number;
  stock_uom?: string;
  purchase_order?: string;
  purchase_order_item?: string;
  rejected_qty?: number;
  rejected_warehouse?: string;
  schedule_date?: string;
  description?: string;
  cost_center?: string;
};

export type PurchaseReceiptCreate = {
  naming_series: "MAT-PRE-.YYYY.-" | "MAT-PR-RET-.YYYY.-";
  supplier: string;
  posting_date: string;
  posting_time: string;
  company: string;
  currency: string;
  conversion_rate: number;
  items: PurchaseReceiptItemCreate[];
  buying_price_list?: string;
  price_list_currency?: string;
  plc_conversion_rate?: number;
  custom_letron_orchestration_id?: string;
  supplier_delivery_note?: string;
  set_warehouse?: string;
  remarks?: string;
};

export type PurchaseReceipt = PurchaseReceiptCreate & {
  name: string;
  posting_time: string;
  docstatus?: 0 | 1 | 2;
  status?: string;
  base_net_total?: number;
  grand_total?: number;
};

export function parsePurchaseReceiptCreate(input: unknown): PurchaseReceiptCreate {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("Purchase Receipt body must be an object.");
  const value = input as Record<string, unknown>;
  const items = value.items;
  if (!Array.isArray(items)) throw new Error("Purchase Receipt items must be an array.");
  const payload: PurchaseReceiptCreate = {
    naming_series: value.naming_series as PurchaseReceiptCreate["naming_series"],
    supplier: typeof value.supplier === "string" ? value.supplier : "",
    posting_date: typeof value.posting_date === "string" ? value.posting_date : "",
    posting_time: typeof value.posting_time === "string" ? value.posting_time : "",
    company: typeof value.company === "string" ? value.company : "",
    currency: typeof value.currency === "string" ? value.currency : "",
    conversion_rate: typeof value.conversion_rate === "number" ? value.conversion_rate : Number.NaN,
    items: items.map((raw, index) => {
      if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`Purchase Receipt item ${index} must be an object.`);
      const item = raw as Record<string, unknown>;
      return {
        item_code: typeof item.item_code === "string" ? item.item_code : "",
        item_name: typeof item.item_name === "string" ? item.item_name : undefined,
        qty: typeof item.qty === "number" ? item.qty : Number.NaN,
        uom: typeof item.uom === "string" ? item.uom : "",
        rate: typeof item.rate === "number" ? item.rate : Number.NaN,
        warehouse: typeof item.warehouse === "string" ? item.warehouse : "",
        conversion_factor: typeof item.conversion_factor === "number" ? item.conversion_factor : Number.NaN,
        stock_uom: typeof item.stock_uom === "string" ? item.stock_uom : undefined,
        purchase_order: typeof item.purchase_order === "string" ? item.purchase_order : undefined,
        purchase_order_item: typeof item.purchase_order_item === "string" ? item.purchase_order_item : undefined,
      };
    }),
    buying_price_list: typeof value.buying_price_list === "string" ? value.buying_price_list : undefined,
    price_list_currency: typeof value.price_list_currency === "string" ? value.price_list_currency : undefined,
    plc_conversion_rate: typeof value.plc_conversion_rate === "number" ? value.plc_conversion_rate : undefined,
    custom_letron_orchestration_id: typeof value.custom_letron_orchestration_id === "string" ? value.custom_letron_orchestration_id : undefined,
    supplier_delivery_note: typeof value.supplier_delivery_note === "string" ? value.supplier_delivery_note : undefined,
    set_warehouse: typeof value.set_warehouse === "string" ? value.set_warehouse : undefined,
    remarks: typeof value.remarks === "string" ? value.remarks : undefined,
  };
  return assertPurchaseReceiptCreate(payload);
}

export function assertPurchaseReceiptCreate(value: PurchaseReceiptCreate): PurchaseReceiptCreate {
  if (value.naming_series !== "MAT-PRE-.YYYY.-" && value.naming_series !== "MAT-PR-RET-.YYYY.-") throw new Error("Purchase Receipt naming_series is invalid.");
  const missing = (["supplier", "company", "posting_date", "currency"] as const).filter((field) => !value[field]);
  if (missing.length) throw new Error(`Purchase Receipt missing required field(s): ${missing.join(", ")}.`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value.posting_date) || Number.isNaN(Date.parse(`${value.posting_date}T00:00:00Z`))) throw new Error("Purchase Receipt posting_date must be YYYY-MM-DD.");
  if (!/^\d{2}:\d{2}:\d{2}$/.test(value.posting_time)) throw new Error("Purchase Receipt posting_time must be HH:mm:ss.");
  if (!Number.isFinite(value.conversion_rate) || value.conversion_rate <= 0) {
    throw new Error("Purchase Receipt requires a positive conversion_rate.");
  }
  if (!value.items.length) throw new Error("Purchase Receipt requires at least one item.");
  for (const [index, item] of value.items.entries()) {
    if (!item.item_code || !item.uom || !item.warehouse) throw new Error(`Purchase Receipt item ${index} is missing item_code, uom or warehouse.`);
    if (!Number.isFinite(item.qty) || item.qty <= 0 || !Number.isFinite(item.rate) || item.rate < 0 || !Number.isFinite(item.conversion_factor) || item.conversion_factor <= 0) {
      throw new Error(`Purchase Receipt item ${index} has invalid qty or rate.`);
    }
  }
  return value;
}
