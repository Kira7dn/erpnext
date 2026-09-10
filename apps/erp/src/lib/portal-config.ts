import "server-only";

function configuredUrl(name: "LETRON_AUTH_BASE_URL"): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value.replace(/\/$/, "");
}

export function portalAuthBaseUrl(): string {
  return configuredUrl("LETRON_AUTH_BASE_URL");
}

export function portalAppBaseUrl(requestOrigin: string): string {
  return new URL(requestOrigin).origin;
}
