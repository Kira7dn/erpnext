import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  ItemResponseSchema,
  MaterialRequestResponseSchema,
  MaterialRequestWriteSchema,
  RequestforQuotationResponseSchema,
  RequestforQuotationWriteSchema,
} from "../../apps/erp/src/generated/zod";
import {
  buildRfqPayload,
  hydrateRfqItems,
  itemsFromCreatedMaterialRequest,
} from "../../apps/erp/src/lib/purchase-orchestration-contract";

function fixture(name: string): Record<string, any> {
  return JSON.parse(readFileSync(resolve(process.cwd(), "tests/fixtures/contracts", name), "utf8"));
}

const materialRequest = fixture("material-request.valid.json");
const itemCode = materialRequest.items[0].item_code;
const stockUom = "Nos";

async function main(): Promise<void> {
  MaterialRequestWriteSchema.parse(materialRequest);
  assert.throws(
    () => MaterialRequestWriteSchema.parse({ ...materialRequest, items: [{ ...materialRequest.items[0], stock_uom: stockUom }] }),
    /Unrecognized key.*stock_uom/,
  );

  const materialRequestResponse = {
    name: "MR-20260912-0001",
    ...materialRequest,
    items: [{ ...materialRequest.items[0], uom: stockUom, stock_uom: stockUom, conversion_factor: 1, name: "mr-item-1" }],
  };
  MaterialRequestResponseSchema.parse(materialRequestResponse);

  const mappedItems = itemsFromCreatedMaterialRequest({
    name: materialRequestResponse.name,
    items: [{ item_code: itemCode, qty: 2, schedule_date: "2026-10-12", warehouse: "Cửa hàng - LTVN" }],
  });
  const hydratedItems = await hydrateRfqItems(mappedItems, async () => ({ stock_uom: stockUom }));

  const rfq = fixture("request-for-quotation.valid.json");
  const mappedRfq = buildRfqPayload(
    materialRequestResponse,
    ["Link Strategy"],
    hydratedItems.map((item) => ({ ...item, material_request_item: "mr-item-1" })),
    "contract-test-orchestration",
  );
  rfq.items = mappedRfq.items;
  rfq.custom_letron_orchestration_id = mappedRfq.custom_letron_orchestration_id;
  RequestforQuotationWriteSchema.parse(rfq);
  assert.throws(
    () => RequestforQuotationWriteSchema.parse({ ...rfq, items: [{ ...rfq.items[0], stock_uom: undefined }] }),
    /expected string/,
  );
  assert.throws(
    () => RequestforQuotationWriteSchema.parse({ ...rfq, items: [{ ...rfq.items[0], conversion_factor: undefined }] }),
    /expected number/,
  );

  RequestforQuotationResponseSchema.parse({ name: "RFQ-20260912-0001", ...rfq });
  ItemResponseSchema.parse({ name: itemCode, stock_uom: stockUom, item_group: "All Item Groups" });

  console.log("contract-test: 8 assertions passed");
}

void main();
