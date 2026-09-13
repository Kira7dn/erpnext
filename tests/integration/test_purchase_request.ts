import { call, data, prefix, assertName, today, type MaterialRequestWrite } from "./fe-gateway";

async function main() {
  const company = process.env.LETRON_TEST_COMPANY ?? "Letron Việt Nam";
  const itemList = data(await call("listItem"));
  const item = process.env.LETRON_TEST_ITEM ?? String((Array.isArray(itemList) ? itemList[0] : undefined)?.name ?? "");
  if (!item) throw new Error("no Item available; set LETRON_TEST_ITEM");
  const warehouse = process.env.LETRON_TEST_WAREHOUSE ?? "Cửa hàng - LTVN";
  const payload: MaterialRequestWrite = { naming_series: "MAT-REQ-.YYYY.-", material_request_type: "Purchase", company, transaction_date: today, items: [{ item_code: item, qty: 1, schedule_date: today, uom: "Nos", warehouse }] };
  const created = data(await call("createMaterialRequest", undefined, payload));
  const name = assertName(created);
  const read = data(await call("getMaterialRequest", name)); assertName(read, name);
  const list = data(await call("listMaterialRequest"));
  if (!Array.isArray(list)) throw new Error("material request list is not an array");
  console.log(`FE_MATERIAL_REQUEST_TEST=PASS prefix=${prefix} material_request=${name}`);
}
main().catch((error) => { console.error(`FE_MATERIAL_REQUEST_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
