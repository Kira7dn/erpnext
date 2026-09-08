import "server-only";

function configuredUrl(name: "LETRON_AUTH_BASE_URL" | "NEXT_PUBLIC_APP_URL", fallback: string): string {
  return (process.env[name] ?? fallback).replace(/\/$/, "");
}

export function portalAuthBaseUrl(): string {
  return configuredUrl("LETRON_AUTH_BASE_URL", "http://localhost:3000");
}

export function portalAppBaseUrl(requestOrigin?: string): string {
  if (requestOrigin) {
    const origin = new URL(requestOrigin);
    if (origin.hostname === "localhost" || origin.hostname === "127.0.0.1") {
      return requestOrigin.replace(/\/$/, "");
    }
  }
  return configuredUrl("NEXT_PUBLIC_APP_URL", requestOrigin ?? "http://localhost:3001");
}
