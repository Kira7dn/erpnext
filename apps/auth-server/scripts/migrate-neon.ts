import { Client } from "@neondatabase/serverless";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { config as loadDotEnv } from "dotenv";

loadDotEnv({ path: resolve(process.cwd(), ".env.local"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), ".env"), override: false, quiet: true });
loadDotEnv({ path: resolve(process.cwd(), "../../.env"), override: false, quiet: true });

const databaseUrl = process.env.DATABASE_URL;
if (!databaseUrl) throw new Error("DATABASE_URL is required for migrations");

const migrationsPath = join(process.cwd(), "prisma", "migrations");
const migrationNames = readdirSync(migrationsPath, { withFileTypes: true })
  .filter(
    (entry) =>
      entry.isDirectory() &&
      /^\d+_/.test(entry.name) &&
      existsSync(join(migrationsPath, entry.name, "migration.sql")),
  )
  .map((entry) => entry.name)
  .sort();

const client = new Client(databaseUrl);
await client.connect();

try {
  await client.query("CREATE TABLE IF NOT EXISTS _prisma_migrations (id VARCHAR(36) NOT NULL PRIMARY KEY, checksum VARCHAR(64) NOT NULL, finished_at TIMESTAMPTZ, migration_name VARCHAR(255) NOT NULL, logs TEXT, rolled_back_at TIMESTAMPTZ, started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, applied_steps_count INTEGER NOT NULL DEFAULT 0)");

  for (const name of migrationNames) {
    const file = join(migrationsPath, name, "migration.sql");
    const sql = readFileSync(file, "utf8");
    const checksum = createHash("sha256").update(sql).digest("hex");
    const existing = await client.query("SELECT checksum, finished_at, rolled_back_at FROM _prisma_migrations WHERE migration_name = $1", [name]);
    const row = existing.rows[0] as { checksum: string; finished_at: Date | null; rolled_back_at: Date | null } | undefined;
    if (row?.finished_at && row.checksum === checksum) continue;
    if (row?.finished_at && row.checksum !== checksum) throw new Error(`Migration checksum mismatch: ${name}`);
    if (row?.rolled_back_at) throw new Error(`Migration was rolled back and must be resolved: ${name}`);

    const id = randomUUID();
    await client.query("BEGIN");
    try {
      await client.query("SELECT pg_advisory_xact_lock(74192602)");
      await client.query(sql);
      await client.query("INSERT INTO _prisma_migrations (id, checksum, finished_at, migration_name, applied_steps_count) VALUES ($1, $2, CURRENT_TIMESTAMP, $3, 1)", [id, checksum, name]);
      await client.query("COMMIT");
      console.log(`applied ${name}`);
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    }
  }
} finally {
  await client.end();
}
