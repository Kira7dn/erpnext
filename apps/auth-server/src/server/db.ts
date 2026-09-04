import { neonConfig } from "@neondatabase/serverless";
import { PrismaNeon } from "@prisma/adapter-neon";
import ws from "ws";

import { PrismaClient } from "../../generated/prisma/client";
import { getEnv } from "./env";

type PrismaGlobal = typeof globalThis & { __letronAuthPrisma?: PrismaClient };

neonConfig.webSocketConstructor = ws;

export function getDb(): PrismaClient {
  const globalScope = globalThis as PrismaGlobal;
  if (!globalScope.__letronAuthPrisma) {
    const adapter = new PrismaNeon({ connectionString: getEnv().DATABASE_URL });
    globalScope.__letronAuthPrisma = new PrismaClient({ adapter });
  }
  return globalScope.__letronAuthPrisma;
}
