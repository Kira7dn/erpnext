import { timingSafeEqual } from "node:crypto";

import type { NextApiRequest } from "next";

import { getDb } from "./db";
import { getEnv } from "./env";
import { LARK_PO_APPROVER_EMAIL } from "./lark-runtime-config";
import type { AuthenticatedUser } from "./session";

function suppliedApiKey(req: NextApiRequest): string {
  const authorization = req.headers.authorization;
  return typeof authorization === "string" ? authorization.replace(/^Bearer\s+/i, "") : "";
}

function matchesApiKey(supplied: string, expected: string): boolean {
  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  return left.length === right.length && left.length > 0 && timingSafeEqual(left, right);
}

/** Resolve the configured test credential to one existing Lark identity. */
export async function authenticateTestCredential(req: NextApiRequest): Promise<AuthenticatedUser | null> {
  const env = getEnv();
  const testUserEmail = LARK_PO_APPROVER_EMAIL.toLowerCase();
  if (!env.LETRON_INTERNAL_API_SECRET || !matchesApiKey(suppliedApiKey(req), env.LETRON_INTERNAL_API_SECRET)) return null;

  const user = await getDb().user.findUnique({
    where: { email: testUserEmail },
    include: {
      identities: {
        where: {
          provider: "lark",
          tenantKey: env.LARK_ALLOWED_TENANT_KEY,
          subjectType: "union_id",
        },
        orderBy: { id: "asc" },
        take: 1,
      },
    },
  });
  const identity = user?.identities[0];
  if (!user || user.status !== "ACTIVE" || !identity || identity.email?.toLowerCase() !== user.email.toLowerCase()) return null;

  return {
    id: user.id,
    email: user.email,
    displayName: user.displayName,
    avatarUrl: user.avatarUrl,
    groupIds: identity.groupIds,
    tenantKey: identity.tenantKey,
    subject: identity.subject,
    subjectType: identity.subjectType,
  };
}
