"""Build the single public business endpoint registry.

The registry is deliberately smaller than OpenAPI.  It is the shared
authorization and dispatch index: every public operation has one stable id,
one canonical route, and one native target.  OpenAPI remains the contract for
request/response schemas.
"""

from typing import Any


def _risk(method: str, operation: str, path: str) -> str:
    if method == "DELETE" or path.endswith(("/submit", "/cancel")):
        return "high"
    if operation in {"create", "update"} or method in {"POST", "PUT", "PATCH"}:
        return "medium"
    return "low"


def build_registry(spec: dict[str, Any], contract: dict[str, Any]) -> list[dict[str, Any]]:
    aliases = {item["doctype"]: item["path"] for item in contract["runtime"].get("public_resources", [])}
    reverse_aliases = {path: doctype for doctype, path in aliases.items()}
    dependencies = contract["runtime"].get("permission_dependencies", {})
    registry: list[dict[str, Any]] = []
    for path, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            operation_id = operation.get("operationId")
            public_operation = operation.get("x-public-operation")
            if not isinstance(operation_id, str) or not isinstance(public_operation, str):
                continue
            parts = path.strip("/").split("/")
            if len(parts) < 4 or parts[:2] != ["api", "v1"]:
                continue
            module, resource = parts[2:4]
            doctype = reverse_aliases.get(path) or reverse_aliases.get(path.split("/{", 1)[0])
            action = parts[-1] if len(parts) >= 6 and not parts[-1].startswith("{") else None
            target: dict[str, str] = {}
            if doctype:
                target["doctype"] = doctype
                if action:
                    target["action"] = action
            handler = operation.get("x-frappe-handler")
            if isinstance(handler, str):
                target["handler"] = handler
            registry.append({
                "operation_id": operation_id,
                "module": module,
                "resource": resource,
                "method": method.upper(),
                "path": path,
                "operation": public_operation,
                "risk": _risk(method.upper(), public_operation, path),
                "target": target,
                "dependencies": sorted(dependencies.get(f"{module}/{resource}", [])),
                "request_schema": (operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
                                    if isinstance(operation.get("requestBody"), dict) else None),
                "response_schema": (operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema")
                                     if isinstance(operation.get("responses", {}).get("200"), dict) else None),
            })
    return sorted(registry, key=lambda item: (item["path"], item["method"], item["operation_id"]))
