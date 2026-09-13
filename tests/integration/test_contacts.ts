import { call, data, prefix, assertName, type AddressWrite, type ContactWrite } from "./fe-gateway";

async function main() {
  const address: AddressWrite = { address_title: `${prefix} Address`, address_type: "Billing", address_line1: "1 Letron Street", city: "Da Nang", country: "Vietnam" };
  const addressRow = data(await call("createAddress", undefined, address));
  const addressName = assertName(addressRow);
  const addressRead = data(await call("getAddress", addressName)); assertName(addressRead, addressName);
  const addressUpdate: AddressWrite = { ...address, name: addressName, city: "Hue" };
  assertName(data(await call("updateAddress", addressName, addressUpdate)), addressName);
  const contact: ContactWrite = { first_name: `${prefix} Contact`, last_name: "Integration" };
  const contactRow = data(await call("createContact", undefined, contact));
  const contactName = assertName(contactRow);
  assertName(data(await call("getContact", contactName)), contactName);
  assertName(data(await call("updateContact", contactName, { ...contact, name: contactName, last_name: "Updated" })), contactName);
  console.log(`FE_CONTACTS_TEST=PASS prefix=${prefix} address=${addressName} contact=${contactName}`);
}
main().catch((error) => { console.error(`FE_CONTACTS_TEST=FAIL ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1; });
