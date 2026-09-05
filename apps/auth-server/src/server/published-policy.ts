import { getDb } from "./db";
import { parseAccessPolicy, type AccessPolicy } from "./access-policy";

export async function getPublishedPolicy(): Promise<{ policy: AccessPolicy; version: number; sha256: string } | null> {
  const row = await getDb().accessPolicy.findFirst({ where: { status: "PUBLISHED" }, orderBy: { version: "desc" } });
  if (!row) return null;
  return { policy: parseAccessPolicy(row.policy), version: row.version, sha256: row.sha256 };
}
