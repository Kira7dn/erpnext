import { randomBytes } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import type { ClientMetadata } from "oidc-provider";
import type { Prisma } from "../generated/prisma/client";
import { encrypt } from "../src/server/crypto";
import { getDb } from "../src/server/db";
import { getEnv } from "../src/server/env";
import { getOidcProvider } from "../src/server/oidc";

const rootEnvPath = resolve(process.cwd(), "../../.env");
const authEnvPath = resolve(process.cwd(), ".env");
const rootEnv = await readFile(rootEnvPath, "utf8");
const authEnv = await readFile(authEnvPath, "utf8");

function valueOf(source: string, name: string): string | undefined {
  const match = source.match(new RegExp(`^${name}=(.*)$`, "m"));
  return match?.[1]?.trim().replace(/^(['"])(.*)\1$/, "$2");
}

function upsert(source: string, name: string, value: string): string {
  const line = `${name}=${value}`;
  const pattern = new RegExp(`^${name}=.*$`, "m");
  if (pattern.test(source)) return source.replace(pattern, line);
  return `${source.replace(/\s*$/, "")}\n${line}\n`;
}

const env = getEnv();
const issuer = `${env.AUTH_BASE_URL}/api/oidc`;
const publicAuthUrl = new URL(env.AUTH_BASE_URL);
const internalAuthUrl = new URL(env.AUTH_BASE_URL);
if (["localhost", "127.0.0.1"].includes(publicAuthUrl.hostname)) {
  internalAuthUrl.hostname = "host.docker.internal";
}
const internalIssuer = `${internalAuthUrl.toString().replace(/\/$/, "")}/api/oidc`;
const clientId = valueOf(rootEnv, "LETRON_SSO_CLIENT_ID") || "letron-erp";
const clientSecret = valueOf(rootEnv, "LETRON_SSO_CLIENT_SECRET") || randomBytes(32).toString("base64url");
const syncSecret = valueOf(rootEnv, "LETRON_SSO_SYNC_SECRET") || randomBytes(32).toString("base64url");
const erpBaseUrl = (valueOf(rootEnv, "LETRON_SSO_ERP_BASE_URL") || "http://localhost:8080").replace(/\/$/, "");
const redirectUri = `${erpBaseUrl}/api/method/letron_api.sso.callback`;
const syncUrl = `${internalAuthUrl.toString().replace(/\/$/, "")}/api/internal/lark-role-snapshots`;

const metadata: ClientMetadata = {
  client_id: clientId,
  client_name: "Letron ERPNext",
  redirect_uris: [redirectUri],
  post_logout_redirect_uris: [`${erpBaseUrl}/login`],
  response_types: ["code"],
  grant_types: ["authorization_code"],
  token_endpoint_auth_method: "client_secret_basic",
  application_type: "web",
  id_token_signed_response_alg: "RS256",
};

await getOidcProvider().Client.validate({ ...metadata, client_secret: clientSecret });
await getDb().oidcClient.upsert({
  where: { clientId },
  create: {
    clientId,
    metadata: metadata as Prisma.InputJsonValue,
    encryptedClientSecret: encrypt(clientSecret),
  },
  update: {
    metadata: metadata as Prisma.InputJsonValue,
    encryptedClientSecret: encrypt(clientSecret),
    active: true,
  },
});

let updatedRootEnv = rootEnv;
for (const [name, value] of Object.entries({
  LETRON_SSO_ISSUER: issuer,
  LETRON_SSO_INTERNAL_ISSUER: internalIssuer,
  LETRON_SSO_CLIENT_ID: clientId,
  LETRON_SSO_CLIENT_SECRET: clientSecret,
  LETRON_SSO_ERP_BASE_URL: erpBaseUrl,
  LETRON_SSO_ROLE_SYNC_ENABLED: valueOf(rootEnv, "LETRON_SSO_ROLE_SYNC_ENABLED") || "false",
  LETRON_SSO_SYNC_URL: syncUrl,
  LETRON_SSO_SYNC_SECRET: syncSecret,
  LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS:
    valueOf(rootEnv, "LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS") || "60",
})) {
  updatedRootEnv = upsert(updatedRootEnv, name, value);
}
await writeFile(rootEnvPath, updatedRootEnv, { encoding: "utf8", mode: 0o600 });

let updatedAuthEnv = authEnv;
updatedAuthEnv = upsert(updatedAuthEnv, "LARK_GROUP_SYNC_ENABLED", valueOf(authEnv, "LARK_GROUP_SYNC_ENABLED") || "false");
updatedAuthEnv = upsert(updatedAuthEnv, "AUTH_ERP_SYNC_SECRET", syncSecret);
await writeFile(authEnvPath, updatedAuthEnv, { encoding: "utf8", mode: 0o600 });

console.log(`Provisioned OIDC client ${clientId}`);
console.log(`redirect_uri=${redirectUri}`);
console.log(`issuer=${issuer}`);
console.log("Client secret was written to the ignored repository .env and was not printed.");
console.log("The role-sync secret was written to both ignored .env files and was not printed.");
await getDb().$disconnect();
