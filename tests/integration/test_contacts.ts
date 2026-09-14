import { call, data, prefix, assertName, type ContactWrite } from "./fe-gateway";

async function main() {
  const contact: ContactWrite = { first_name: `${prefix} Contact`, last_name: "Integration" };
  const contactRow = data(await call("createContact", undefined, contact));
  const contactName = assertName(contactRow);
  assertName(data(await call("getContact", contactName)), contactName);
  assertName(data(await call("updateContact", contactName, { ...contact, name: contactName, last_name: "Updated" })), contactName);
  console.log(`FE_CONTACT_TEST=PASS prefix=${prefix} contact=${contactName}`);
}
main().catch((error) => { console.error(`FE_CONTACT_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
