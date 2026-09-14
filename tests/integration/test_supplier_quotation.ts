import { call, data, prefix, assertName, policyPurchaseContext, today, type RequestforQuotationWrite, type SupplierQuotationWrite } from "./fe-gateway";

async function main() {
  const { company, warehouse, item } = await policyPurchaseContext();
  const supplier = process.env.LETRON_TEST_SUPPLIER ?? "Link Strategy";
  const mr = data(await call("createMaterialRequest", undefined, { naming_series: "MAT-REQ-.YYYY.-", material_request_type: "Purchase", company, transaction_date: today, items: [{ item_code: item, qty: 1, schedule_date: today, uom: "Nos", warehouse }] }));
  const mrName = assertName(mr);
  const mrItemName = String((mr.items as Array<Record<string, unknown>> | undefined)?.[0]?.name ?? "");
  if (!mrItemName) throw new Error(`Material Request ${mrName} has no item to link RFQ`);
  const rfqPayload: RequestforQuotationWrite = { naming_series: "RQF-.YYYY.-", company, transaction_date: today, subject: `${prefix} RFQ`, suppliers: [{ supplier }], items: [{ item_code: item, qty: 1, schedule_date: today, uom: "Nos", warehouse, conversion_factor: 1, stock_uom: "Nos", material_request_item: mrItemName }] };
  const rfq = data(await call("createRequestforQuotation", undefined, rfqPayload));
  const rfqName = assertName(rfq);
  assertName(data(await call("getRequestforQuotation", rfqName)), rfqName);
  const rfqItemName = String((rfq.items as Array<Record<string, unknown>> | undefined)?.[0]?.name ?? "");
  if (!rfqItemName) throw new Error(`RFQ ${rfqName} has no item to link Supplier Quotation`);
  const sqPayload: SupplierQuotationWrite = { naming_series: "SUP-QUO-.YYYY.-", supplier, company, transaction_date: today, currency: "VND", conversion_rate: 1, items: [{ item_code: item, qty: 1, uom: "Nos", warehouse, rate: 1000, request_for_quotation: rfqName, request_for_quotation_item: rfqItemName, material_request: mrName, material_request_item: mrItemName }] };
  const sq = data(await call("createSupplierQuotation", undefined, sqPayload));
  const sqName = assertName(sq);
  if (String((sq.items as Array<Record<string, unknown>> | undefined)?.[0]?.request_for_quotation ?? rfqName) !== rfqName) throw new Error(`supplier quotation is not linked to RFQ ${rfqName}`);
  assertName(data(await call("getSupplierQuotation", sqName)), sqName);
  const submitted = await call("submitSupplierQuotation", sqName); const submittedRow = data(submitted);
  assertName(submittedRow, sqName); if (Number(submittedRow.docstatus) !== 1) throw new Error(`SQ ${sqName} was not submitted`);
  const po = data(await call("makePurchaseOrderFromSupplierQuotation", sqName, {}));
  const poName = assertName(po);
  console.log(`FE_SUPPLIER_QUOTATION_TEST=PASS prefix=${prefix} mr=${mrName} rfq=${rfqName} supplier_quotation=${sqName} purchase_order=${poName}`);
}
main().catch((error) => { console.error(`FE_SUPPLIER_QUOTATION_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
