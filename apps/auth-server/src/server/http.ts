import type { NextApiRequest, NextApiResponse } from "next";

export function firstQueryValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function parseCookies(header: string | undefined): Record<string, string> {
  if (!header) return {};
  return Object.fromEntries(
    header.split(";").flatMap((entry) => {
      const separator = entry.indexOf("=");
      if (separator < 1) return [];
      const key = entry.slice(0, separator).trim();
      const raw = entry.slice(separator + 1).trim();
      try {
        return [[key, decodeURIComponent(raw)]];
      } catch {
        return [];
      }
    }),
  );
}

export function appendSetCookie(res: NextApiResponse, value: string): void {
  const current = res.getHeader("Set-Cookie");
  const values = current ? (Array.isArray(current) ? current.map(String) : [String(current)]) : [];
  res.setHeader("Set-Cookie", [...values, value]);
}

export function serializeCookie(
  name: string,
  value: string,
  options: { maxAge?: number; expires?: Date; secure?: boolean; domain?: string } = {},
): string {
  const parts = [`${name}=${encodeURIComponent(value)}`, "Path=/", "HttpOnly", "SameSite=Lax"];
  if (options.domain) parts.push(`Domain=${options.domain}`);
  if (options.maxAge !== undefined) parts.push(`Max-Age=${Math.max(0, Math.floor(options.maxAge))}`);
  if (options.expires) parts.push(`Expires=${options.expires.toUTCString()}`);
  if (options.secure) parts.push("Secure");
  return parts.join("; ");
}

export function requestId(req: NextApiRequest): string {
  const header = firstQueryValue(req.headers["x-request-id"]);
  return header?.slice(0, 128) || crypto.randomUUID();
}

export function requestIsSecure(req: NextApiRequest): boolean {
  const forwarded = firstQueryValue(req.headers["x-forwarded-proto"]);
  if (forwarded) return forwarded === "https";
  return Boolean((req.socket as typeof req.socket & { encrypted?: boolean }).encrypted);
}

export function redirectError(res: NextApiResponse, code: string): void {
  res.redirect(303, `/error?code=${encodeURIComponent(code)}`);
}

export function disableCaching(res: NextApiResponse): void {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("Pragma", "no-cache");
}
