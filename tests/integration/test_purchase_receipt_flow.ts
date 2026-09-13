import { call, data, prefix, assertName, assertSubmitted, today, type PurchaseOrderWrite, type PurchaseReceiptWrite } from "./fe-gateway";

async function main() {
  const company = process.env.LETRON_TEST_COMPANY ?? "Letron Việt Nam";
  const supplier = process.env.LETRON_TEST_SUPPLIER ?? "Link Strategy";
  const itemList = data(await call("listItem"));
  const item = process.env.LETRON_TEST_ITEM ?? String((Array.isArray(itemList) ? itemList[0] : undefined)?.name ?? "");
  if (!item) throw new Error("no Item available; set LETRON_TEST_ITEM");
  const warehouse = process.env.LETRON_TEST_WAREHOUSE ?? "Cửa hàng - LTVN";
  const po: PurchaseOrderWrite = { naming_series: "PUR-ORD-.YYYY.-", supplier, company, transaction_date: today, schedule_date: today, currency: "VND", conversion_rate: 1, items: [{ item_code: item, item_name: item, schedule_date: today, qty: 1, uom: "Nos", rate: 1000, warehouse }] };
  const poRow = data(await call("createPurchaseOrder", undefined, po)); const poName = assertName(poRow);
  assertSubmitted(data(await call("submitPurchaseOrder", poName)), poName);
  const receipt: PurchaseReceiptWrite = { naming_series: "MAT-PRE-.YYYY.-", supplier, company, posting_date: today, posting_time: new Date().toISOString().slice(11, 19), currency: "VND", conversion_rate: 1, supplier_delivery_note: `${prefix}-DELIVERY`, items: [{ item_code: item, item_name: item, qty: 1, uom: "Nos", stock_uom: "Nos", conversion_factor: 1, rate: 1000, warehouse, purchase_order: poName }] };
  const receiptRow = data(await call("createPurchaseReceipt", undefined, receipt)); const receiptName = assertName(receiptRow);
  assertSubmitted(data(await call("submitPurchaseReceipt", receiptName)), receiptName);
  const read = data(await call("getPurchaseReceipt", receiptName)); assertName(read, receiptName); if (String(read.supplier_delivery_note) !== `${prefix}-DELIVERY`) throw new Error("supplier delivery note was not persisted");
  console.log(`FE_PURCHASE_RECEIPT_TEST=PASS prefix=${prefix} purchase_order=${poName} purchase_receipt=${receiptName} supplier_notification=BACKEND_SUBMIT_SIDE_EFFECT`);
}
main().catch((error) => { console.error(`FE_PURCHASE_RECEIPT_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
