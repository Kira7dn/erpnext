import { randomBytes } from "node:crypto";

import type { ClientMetadata } from "oidc-provider";
import type { Prisma } from "../generated/prisma/client";
import { encrypt } from "../src/server/crypto";
import { getDb } from "../src/server/db";
import { getOidcProvider } from "../src/server/oidc";

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

const clientId = argument("--id");
const redirectUri = argument("--redirect-uri");
const publicClient = process.argv.includes("--public");
if (!clientId || !/^[a-zA-Z0-9._-]{3,100}$/.test(clientId)) {
  throw new Error("--id is required and must contain 3-100 letters, digits, dot, underscore, or dash");
}
if (!redirectUri) throw new Error("--redirect-uri is required");
const redirect = new URL(redirectUri);
if (redirect.protocol !== "https:" && redirect.hostname !== "localhost" && redirect.hostname !== "127.0.0.1") {
  throw new Error("Redirect URI must use HTTPS except for loopback development callbacks");
}

const clientSecret = publicClient ? undefined : randomBytes(32).toString("base64url");
const metadata: ClientMetadata = {
  client_id: clientId,
  client_name: clientId,
  redirect_uris: [redirectUri],
  response_types: ["code"],
  grant_types: ["authorization_code"],
  token_endpoint_auth_method: publicClient ? "none" : "client_secret_basic",
  application_type: "web",
  id_token_signed_response_alg: "RS256",
};

await getOidcProvider().Client.validate({
  ...metadata,
  ...(clientSecret ? { client_secret: clientSecret } : {}),
});
await getDb().oidcClient.upsert({
  where: { clientId },
  create: {
    clientId,
    metadata: metadata as Prisma.InputJsonValue,
    encryptedClientSecret: clientSecret ? encrypt(clientSecret) : null,
  },
  update: {
    metadata: metadata as Prisma.InputJsonValue,
    encryptedClientSecret: clientSecret ? encrypt(clientSecret) : null,
    active: true,
  },
});

console.log(`client_id=${clientId}`);
console.log(`token_endpoint_auth_method=${metadata.token_endpoint_auth_method}`);
if (clientSecret) console.log(`client_secret=${clientSecret}`);
console.log("Store the client secret now; it will not be printed again.");
await getDb().$disconnect();
