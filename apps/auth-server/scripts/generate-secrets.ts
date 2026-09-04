import { randomBytes } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { exportJWK, generateKeyPair } from "jose";

const { privateKey } = await generateKeyPair("RS256", { extractable: true, modulusLength: 3072 });
const privateJwk = await exportJWK(privateKey);
privateJwk.alg = "RS256";
privateJwk.use = "sig";
privateJwk.kid = randomBytes(12).toString("hex");

const values = {
  AUTH_DATA_ENCRYPTION_KEY: randomBytes(32).toString("base64"),
  OIDC_COOKIE_KEYS: JSON.stringify([
  randomBytes(32).toString("base64url"),
  randomBytes(32).toString("base64url"),
  ]),
  OIDC_JWKS: JSON.stringify({ keys: [privateJwk] }),
};

function argument(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function setEnvValue(content: string, name: string, value: string): string {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const index = lines.findIndex((line) => line.startsWith(`${name}=`));
  if (index >= 0) lines[index] = `${name}=${value}`;
  else lines.push(`${name}=${value}`);
  return lines.join("\n");
}

if (process.argv.includes("--write-env")) {
  const tenantKey = argument("--tenant-key");
  if (!tenantKey) throw new Error("--tenant-key is required with --write-env");
  const envPath = resolve(process.cwd(), ".env");
  let content = await readFile(envPath, "utf8");
  content = setEnvValue(content, "LARK_ALLOWED_TENANT_KEY", tenantKey);
  content = setEnvValue(content, "AUTH_DATA_ENCRYPTION_KEY", values.AUTH_DATA_ENCRYPTION_KEY);
  content = setEnvValue(content, "OIDC_COOKIE_KEYS", values.OIDC_COOKIE_KEYS);
  content = setEnvValue(content, "OIDC_JWKS", values.OIDC_JWKS);
  await writeFile(envPath, content.endsWith("\n") ? content : `${content}\n`, "utf8");
  console.log("Updated .env with the tenant key and newly generated auth secrets.");
} else {
  console.log(`AUTH_DATA_ENCRYPTION_KEY=${values.AUTH_DATA_ENCRYPTION_KEY}`);
  console.log(`OIDC_COOKIE_KEYS=${values.OIDC_COOKIE_KEYS}`);
  console.log(`OIDC_JWKS=${values.OIDC_JWKS}`);
}
