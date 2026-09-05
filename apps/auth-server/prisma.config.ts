import { config as loadDotEnv } from "dotenv";
import { resolve } from "node:path";
import { defineConfig } from "prisma/config";

loadDotEnv({ path: resolve(process.cwd(), ".env.local"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), ".env"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), "../../.env"), override: false, quiet: true });

const allowsPlaceholder = process.argv.some((value) => value === "generate" || value === "validate");
const runtimeDatabaseUrl = process.env.DATABASE_URL
  ?? (allowsPlaceholder ? "postgresql://build:build@127.0.0.1:5432/build" : undefined);
if (!runtimeDatabaseUrl) throw new Error("DATABASE_URL is required for Prisma migration commands");

// Neon uses the pooled hostname for runtime traffic and the non-pooled
// hostname for Prisma CLI operations such as migrations. Keep one secret in
// configuration and derive the direct endpoint instead of adding another env.
const databaseUrl = runtimeDatabaseUrl.replace(/-pooler\./, ".");

export default defineConfig({
  schema: "prisma/schema.prisma",
  migrations: {
    path: "prisma/migrations",
  },
  datasource: {
    // Prisma generate/validate do not connect to the placeholder. Migration
    // commands fail above unless a real DATABASE_URL is configured.
    url: databaseUrl,
  },
});
