import { call, data, prefix } from "./fe-gateway";

async function main() {
  const form = new FormData();
  form.set("file", new Blob([`Letron FE gateway attachment ${prefix}`], { type: "text/plain" }), `${prefix}.txt`);
  form.set("attached_to_doctype", "Material Request");
  const existing = data(await call("listMaterialRequest"));
  const target = process.env.LETRON_TEST_ATTACHMENT_NAME ?? String((Array.isArray(existing) ? existing[0] : undefined)?.name ?? "");
  if (!target) throw new Error("no Material Request available for attachment target; set LETRON_TEST_ATTACHMENT_NAME");
  form.set("attached_to_name", target);
  form.set("is_private", "1");
  const response = data(await call("createAttachment", `?attached_to_doctype=Material%20Request&attached_to_name=${encodeURIComponent(target)}&is_private=1`, form));
  if (!response.file_url && !response.name) throw new Error(`attachment response has no persisted identity: ${JSON.stringify(response)}`);
  console.log(`FE_ATTACHMENT_TEST=PASS prefix=${prefix} attachment=${String(response.name ?? response.file_url)}`);
}
main().catch((error) => { console.error(`FE_ATTACHMENT_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
