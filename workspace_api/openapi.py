from typing import Any

from .models import DocType, WhitelistedMethod


def _schema(dt: DocType) -> dict[str, Any]:
    properties: dict[str, Any] = {"name": {"type": "string"}}
    required = ["name"]
    for field in dt.fields:
        kind = {"Int": "integer", "Float": "number", "Check": "boolean", "Date": "string", "Datetime": "string"}.get(field.fieldtype, "string")
        item: dict[str, Any] = {"type": kind}
        if field.fieldtype in {"Date", "Datetime"}:
            item["format"] = "date" if field.fieldtype == "Date" else "date-time"
        if field.options:
            item["x-frappe-options"] = field.options
        properties[field.fieldname] = item
        if field.reqd:
            required.append(field.fieldname)
    out: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": True}
    if required:
        out["required"] = sorted(set(required))
    return out


def build_openapi(contract: dict[str, Any], doctypes: list[DocType], methods: list[WhitelistedMethod]) -> dict[str, Any]:
    schemas = {dt.name.replace(" ", ""): _schema(dt) for dt in doctypes}
    schemas["FrappeResponse"] = {"type": "object", "properties": {"message": {}}}
    paths: dict[str, Any] = {}
    if contract["runtime"].get("include_generic_resource_api"):
        paths["/api/resource/{doctype}"] = {
            "parameters": [{"name": "doctype", "in": "path", "required": True, "schema": {"type": "string"}}],
            "get": {"operationId": "listResource", "responses": {"200": {"description": "Resource list", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/FrappeResponse"}}}}}},
            "post": {"operationId": "createResource", "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "Created resource"}}},
        }
        paths["/api/resource/{doctype}/{name}"] = {
            "parameters": [{"name": "doctype", "in": "path", "required": True, "schema": {"type": "string"}}, {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
            "get": {"operationId": "getResource", "responses": {"200": {"description": "Resource"}}},
            "put": {"operationId": "updateResource", "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}, "responses": {"200": {"description": "Updated resource"}}},
            "delete": {"operationId": "deleteResource", "responses": {"200": {"description": "Deleted resource"}}},
        }
    for method in methods:
        paths[f"/api/method/{method.dotted_path}"] = {"post": {"operationId": method.dotted_path.replace(".", "_"), "x-source": method.source, "responses": {"200": {"description": "Frappe method response"}}}}
    paths["/api/method/frappe.desk.form.load.getdoctype"] = {"get": {"operationId": "getDocTypeMetadata", "responses": {"200": {"description": "DocType metadata"}}}}
    return {"openapi": contract["runtime"]["openapi_version"], "info": {"title": "Letron ERPNext Integration API", "version": "0.1.0"}, "servers": [{"url": "http://localhost:8080"}], "paths": paths, "components": {"schemas": schemas}, "x-contract": contract}
