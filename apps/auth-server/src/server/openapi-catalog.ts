import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type CatalogOperation = "list" | "read" | "create" | "update" | "delete";
type RegistryEntry = { operation_id: string; module: string; resource: string; method: string; path: string; operation: CatalogOperation; target?: Record<string, string> };
type RegistryDocument = { version: number; registry_version?: number; sha256?: string; registry_sha256?: string; operations: RegistryEntry[] };

export type OpenApiPermission = { key: string; module: string; resource: string; label: string; operation: string; operationId: string; method: string; path: string };

const humanize = (value: string) => value.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

let cachedRegistry: RegistryDocument | undefined;

function readRegistry(): RegistryDocument {
  cachedRegistry ??= JSON.parse(readFileSync(resolve(process.cwd(), "../../contracts/generated/registry.json"), "utf8")) as RegistryDocument;
  return cachedRegistry;
}

export function openApiPermissions(): OpenApiPermission[] {
  const permissions = new Map<string, OpenApiPermission>();
  for (const entry of readRegistry().operations) {
    const key = `${entry.module}/${entry.resource}:${entry.operation}`;
    if (!permissions.has(key)) permissions.set(key, { key, module: entry.module, resource: entry.resource, label: humanize(entry.resource), operation: entry.operation, operationId: entry.operation_id, method: entry.method, path: entry.path });
  }
  return [...permissions.values()].sort((a, b) => `${a.module}/${a.resource}/${a.operation}`.localeCompare(`${b.module}/${b.resource}/${b.operation}`));
}

export function registryMetadata(): { version: number; sha256: string } {
  const registry = readRegistry();
  const version = registry.registry_version ?? registry.version;
  const sha256 = registry.registry_sha256 ?? registry.sha256;
  if (!Number.isInteger(version) || typeof sha256 !== "string" || !/^[a-f0-9]{64}$/.test(sha256)) {
    throw new Error("Generated API registry metadata is missing or invalid");
  }
  return { version, sha256 };
}

export function openApiRouteOperations(): Array<{ method: string; path: string; module: string; resource: string; operation: CatalogOperation }> {
  return readRegistry().operations.map(({ method, path, module, resource, operation }) => ({ method, path, module, resource, operation }));
}

export function openApiActionPaths(): Set<string> {
  const actions = new Set<string>();
  for (const entry of readRegistry().operations) {
    const action = entry.target?.action;
    const match = entry.path.match(/^\/api\/v1\/([^/]+)\/([^/]+)\/\{[^/]+\}\/[^/]+$/);
    if (action && match) actions.add(`${match[1]}/${match[2]}/${action}`);
  }
  return actions;
}

export function openApiResourceKeys(): Set<string> {
  return new Set(openApiPermissions().map((permission) => `${permission.module}/${permission.resource}`));
}
