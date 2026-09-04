import type { Prisma } from "../../generated/prisma/client";
import { getDb } from "./db";

export async function audit(input: {
  eventType: string;
  outcome: "success" | "failure";
  userId?: string;
  clientId?: string;
  requestId?: string;
  detail?: Prisma.InputJsonValue;
}): Promise<void> {
  await getDb().auditEvent.create({
    data: {
      eventType: input.eventType,
      outcome: input.outcome,
      userId: input.userId,
      clientId: input.clientId,
      requestId: input.requestId,
      detail: input.detail,
    },
  });
}
