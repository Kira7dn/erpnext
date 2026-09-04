import { config as loadDotEnv } from "dotenv";
import { resolve } from "node:path";
import { defineConfig } from "prisma/config";

loadDotEnv({ path: resolve(process.cwd(), ".env.local"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), ".env"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), "../../.env"), override: false, quiet: true });

const allowsPlaceholder = process.argv.some((value) => value === "generate" || value === "validate");
const databaseUrl = process.env.DATABASE_URL
  ?? (allowsPlaceholder ? "postgresql://build:build@127.0.0.1:5432/build" : undefined);
if (!databaseUrl) throw new Error("DATABASE_URL is required for Prisma migration commands");

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
