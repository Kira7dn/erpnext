import { call, data, prefix, assertName, type SupplierWrite } from "./fe-gateway";

async function main() {
  const list = data(await call("listSupplier"));
  if (!Array.isArray(list)) throw new Error(`supplier list is not an array: ${JSON.stringify(list)}`);
  const supplier = String(process.env.LETRON_TEST_SUPPLIER ?? "Link Strategy");
  const detail = data(await call("getSupplier", supplier));
  assertName(detail, supplier);
  const payload: SupplierWrite = { supplier_name: String(detail.supplier_name ?? supplier), supplier_type: (detail.supplier_type as SupplierWrite["supplier_type"]) ?? "Company", supplier_details: `${prefix} updated` };
  const updated = data(await call("updateSupplier", supplier, payload));
  assertName(updated, supplier);
  console.log(`FE_SUPPLIER_TEST=PASS prefix=${prefix} supplier=${supplier}`);
}
main().catch((error) => { console.error(`FE_SUPPLIER_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
