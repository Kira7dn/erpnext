import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type OpenApiOperation = Record<string, unknown>;
type OpenApiDocument = { paths?: Record<string, Record<string, OpenApiOperation>> };
type CatalogOperation = "list" | "read" | "create" | "update" | "delete";

export type OpenApiPermission = { key: string; module: string; resource: string; label: string; operation: string; operationId: string; method: string; path: string };

const operationNames: Record<string, string> = { GET: "read", POST: "create", PUT: "update", PATCH: "update", DELETE: "delete" };
const actionCapabilities: Record<string, string> = { submit: "update", reconcile: "update", unreconcile: "update", cancel: "delete" };
const humanize = (value: string) => value.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

let cachedOpenApi: OpenApiDocument | undefined;

function readOpenApi(): OpenApiDocument {
  cachedOpenApi ??= JSON.parse(readFileSync(resolve(process.cwd(), "../../contracts/openapi/public.json"), "utf8")) as OpenApiDocument;
  return cachedOpenApi;
}

export function openApiPermissions(): OpenApiPermission[] {
  const openApi = readOpenApi();
  const permissions = new Map<string, OpenApiPermission>();
  for (const [path, definition] of Object.entries(openApi.paths ?? {})) {
    const match = path.match(/^\/api\/v1\/([^/]+)\/([^/]+)/);
    if (!match) continue;
    const [, module, resource] = match;
    for (const [method, operation] of Object.entries(definition ?? {})) {
      if (!operation || typeof operation !== "object") continue;
      const normalizedMethod = method.toUpperCase();
      const action = ["submit", "cancel", "reconcile", "unreconcile"].find((candidate) => path.endsWith(`/${candidate}`));
      const itemPath = /^\/api\/v1\/[^/]+\/[^/]+\/\{[^/]+\}/.test(path);
      const operationName = action ? actionCapabilities[action] : normalizedMethod === "GET" ? (itemPath ? "read" : "list") : operationNames[normalizedMethod];
      if (!operationName) continue;
      const operationId = "operationId" in operation && typeof operation.operationId === "string" ? operation.operationId : `${normalizedMethod} ${path}`;
      const key = `${module}/${resource}:${operationName}`;
      if (!permissions.has(key)) permissions.set(key, { key, module, resource, label: humanize(resource), operation: operationName, operationId, method: normalizedMethod, path });
    }
  }
  return [...permissions.values()].sort((a, b) => `${a.module}/${a.resource}/${a.operation}`.localeCompare(`${b.module}/${b.resource}/${b.operation}`));
}

export function openApiRouteOperations(): Array<{ method: string; path: string; module: string; resource: string; operation: CatalogOperation }> {
  const routes: Array<{ method: string; path: string; module: string; resource: string; operation: CatalogOperation }> = [];
  for (const [path, definition] of Object.entries(readOpenApi().paths ?? {})) {
    const match = path.match(/^\/api\/v1\/([^/]+)\/([^/]+)/);
    if (!match) continue;
    for (const [method, operation] of Object.entries(definition ?? {})) {
      if (!operation || typeof operation !== "object" || !("x-public-operation" in operation)) continue;
      const declared = operation["x-public-operation"];
      if (typeof declared !== "string" || !["list", "read", "create", "update", "delete"].includes(declared)) continue;
      routes.push({ method: method.toUpperCase(), path, module: match[1], resource: match[2], operation: declared as CatalogOperation });
    }
  }
  return routes;
}

export function openApiActionPaths(): Set<string> {
  const actions = new Set<string>();
  for (const path of Object.keys(readOpenApi().paths ?? {})) {
    const match = path.match(/^\/api\/v1\/([^/]+)\/([^/]+)\/\{[^/]+\}\/(submit|cancel|reconcile|unreconcile)$/);
    if (match) actions.add(`${match[1]}/${match[2]}/${match[3]}`);
  }
  return actions;
}

export function openApiResourceKeys(): Set<string> {
  return new Set(openApiPermissions().map((permission) => `${permission.module}/${permission.resource}`));
}
