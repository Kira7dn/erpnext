import hashlib
import os
import re
from typing import Any

from .models import DocType, WhitelistedMethod


def _resource_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if slug.endswith("y") and not slug.endswith(("ay", "ey", "iy", "oy", "uy")):
        return slug[:-1] + "ies"
    if slug.endswith(("s", "x", "ch", "sh")):
        return slug + "es" if not slug.endswith("s") else slug
    return slug + "s"


def _schema_names(doctypes: list[DocType]) -> dict[str, str]:
    result: dict[str, str] = {}
    used: dict[str, str] = {}
    for dt in sorted(doctypes, key=lambda item: item.name):
        base = re.sub(r"[^A-Za-z0-9_]", "", dt.name) or "FrappeDocument"
        name = base
        if name in used and used[name] != dt.name:
            name = f"{base}_{hashlib.sha1(dt.name.encode('utf-8')).hexdigest()[:8]}"
        used[name] = dt.name
        result[dt.name] = name
    return result


def _field_schema(field: Any, names: dict[str, str]) -> dict[str, Any]:
    fieldtype = field.fieldtype
    schema: dict[str, Any]
    if fieldtype in {"Int", "Long Int"}:
        schema = {"type": "integer"}
    elif fieldtype in {"Float", "Currency", "Percent", "Duration"}:
        schema = {"type": "number"}
    elif fieldtype == "Check":
        schema = {"type": "boolean"}
    elif fieldtype == "Date":
        schema = {"type": "string", "format": "date"}
    elif fieldtype == "Datetime":
        schema = {"type": "string", "format": "date-time"}
    elif fieldtype == "Time":
        schema = {"type": "string", "format": "time"}
    elif fieldtype == "Table":
        schema = {"type": "array", "items": {"type": "object"}}
        if field.options in names:
            schema["items"] = {"$ref": f"#/components/schemas/{names[field.options]}"}
    else:
        schema = {"type": "string"}
    if fieldtype == "Select" and field.options:
        schema["enum"] = [line for line in str(field.options).splitlines() if line]
    if fieldtype == "Link" and field.options:
        schema["x-frappe-target-doctype"] = field.options
    if field.options and fieldtype not in {"Select", "Link", "Table"}:
        schema["x-frappe-options"] = field.options
    if getattr(field, "read_only", 0):
        schema["readOnly"] = True
    if getattr(field, "hidden", 0):
        schema["writeOnly"] = True
    return schema


def _schema(dt: DocType, names: dict[str, str]) -> dict[str, Any]:
    properties: dict[str, Any] = {"name": {"type": "string"}}
    required = ["name"]
    for field in dt.fields:
        properties[field.fieldname] = _field_schema(field, names)
        if field.reqd:
            required.append(field.fieldname)
    return {"type": "object", "properties": properties, "required": sorted(set(required)), "additionalProperties": True, "x-module": dt.module or "Uncategorized"}


def _write_schema(schema: dict[str, Any]) -> dict[str, Any]:
    properties = {key: value for key, value in schema["properties"].items() if not value.get("readOnly")}
    required = [key for key in schema.get("required", []) if key in properties]
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": True, "x-module": schema.get("x-module")}


def _response(description: str, schema: dict[str, Any] | None = None, status: str = "200") -> dict[str, Any]:
    response: dict[str, Any] = {"description": description}
    if schema:
        response["content"] = {"application/json": {"schema": schema}}
    return {status: response}


def _json_body(schema: dict[str, Any], required: bool = True) -> dict[str, Any]:
    return {"required": required, "content": {"application/json": {"schema": schema}}}


def _parameter_schema(parameter: dict[str, Any]) -> dict[str, Any]:
    annotation = (parameter.get("annotation") or "").lower()
    if annotation in {"int", "integer"}:
        return {"type": "integer"}
    if annotation in {"float", "decimal"}:
        return {"type": "number"}
    if annotation in {"bool", "boolean"}:
        return {"type": "boolean"}
    return {"type": "string"}


def _rpc_body(method: WhitelistedMethod, generic: bool) -> tuple[dict[str, Any], str]:
    if generic or not method.parameters:
        return {"type": "object", "additionalProperties": True}, "runtime-generic"
    properties = {item["name"]: _parameter_schema(item) for item in method.parameters}
    required = [item["name"] for item in method.parameters if item.get("required")]
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema, "function-signature"


def build_openapi(contract: dict[str, Any], doctypes: list[DocType], methods: list[WhitelistedMethod], module_name: str | None = None) -> dict[str, Any]:
    runtime = contract["runtime"]
    auth_scheme = contract.get("auth", {}).get("scheme", "frappeToken")
    names = _schema_names(doctypes)
    typed = set(runtime.get("typed_doctypes", []))
    public_modules = set(runtime.get("public_modules", []))
    aliases = {item["doctype"]: item["path"] for item in runtime.get("public_resources", [])}
    schemas = {names[dt.name]: _schema(dt, names) for dt in doctypes if dt.name in typed}
    schemas.update({
        "FrappeResponse": {"type": "object", "properties": {"message": {}}, "required": ["message"]},
        "FrappeError": {"type": "object", "properties": {"exc_type": {"type": "string"}, "exception": {"type": "string"}, "_server_messages": {"type": "string"}}},
        "ResourceListResponse": {"type": "object", "properties": {"data": {"type": "array", "items": {"type": "object"}}, "message": {}}},
        "FileUploadResponse": {"type": "object", "properties": {"file_url": {"type": "string"}, "file_name": {"type": "string"}, "message": {}}},
        "PageInfo": {"type": "object", "properties": {"limit_start": {"type": "integer"}, "limit_page_length": {"type": "integer"}}},
    })
    error = {"400": {"description": "Frappe error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/FrappeError"}}}}, "401": {"description": "Authentication required"}, "403": {"description": "Permission denied"}, "404": {"description": "Resource not found"}}
    request_headers = [{"$ref": "#/components/parameters/RequestId"}, {"$ref": "#/components/parameters/IdempotencyKey"}]
    paths: dict[str, Any] = {}
    if module_name is None and runtime.get("include_generic_resource_api"):
        doctype = {"name": "doctype", "in": "path", "required": True, "schema": {"type": "string"}}
        name = {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}
        query = [{"name": "fields", "in": "query", "schema": {"type": "string"}}, {"name": "filters", "in": "query", "schema": {"type": "string"}}, {"name": "order_by", "in": "query", "schema": {"type": "string"}}, {"name": "limit_page_length", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 1000}}, {"name": "limit_start", "in": "query", "schema": {"type": "integer", "minimum": 0}}]
        paths["/api/resource/{doctype}"] = {"parameters": [doctype, *query], "get": {"tags": ["Resource API"], "operationId": "listResource", "parameters": request_headers, "responses": {**_response("Resource list", {"$ref": "#/components/schemas/ResourceListResponse"}), **error}}, "post": {"tags": ["Resource API"], "operationId": "createResource", "parameters": request_headers, "requestBody": _json_body({"type": "object"}), "responses": {**_response("Created resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}}
        paths["/api/resource/{doctype}/{name}"] = {"parameters": [doctype, name], "get": {"tags": ["Resource API"], "operationId": "getResource", "parameters": request_headers, "responses": {**_response("Resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}, "put": {"tags": ["Resource API"], "operationId": "updateResource", "parameters": request_headers, "requestBody": _json_body({"type": "object"}), "responses": {**_response("Updated resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}, "delete": {"tags": ["Resource API"], "operationId": "deleteResource", "parameters": request_headers, "responses": {**_response("Deleted resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}}
    if module_name is None and runtime.get("include_doctype_metadata"):
        paths["/api/method/frappe.desk.form.load.getdoctype"] = {"get": {"tags": ["Metadata"], "operationId": "getDocTypeMetadata", "parameters": [{"name": "doctype", "in": "query", "required": True, "schema": {"type": "string"}}, *request_headers], "responses": {**_response("DocType metadata", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}}
    include = set(runtime.get("include_methods", [])) if runtime.get("include_whitelisted_methods", True) else set()
    for method in methods:
        if module_name is not None:
            continue
        if method.dotted_path not in include:
            continue
        body, source = _rpc_body(method, False)
        operation = {"tags": ["Whitelisted methods"], "operationId": method.dotted_path.replace(".", "_"), "parameters": request_headers, "requestBody": _json_body(body, bool(method.parameters)), "responses": {**_response("Frappe method response", {"$ref": "#/components/schemas/FrappeResponse"}), **error}, "x-source": method.source, "x-schema-source": source}
        if method.allow_guest:
            operation["security"] = []
        verbs = method.methods or ["GET", "POST"]
        path = f"/api/method/{method.dotted_path}"
        paths.setdefault(path, {})
        for verb in verbs:
            paths[path][verb.lower()] = {**operation, "operationId": f"{operation['operationId']}_{verb.lower()}"}
    if module_name is None and runtime.get("include_generic_rpc_fallback"):
        paths["/api/method/{method}"] = {"parameters": [{"name": "method", "in": "path", "required": True, "schema": {"type": "string"}}], "post": {"tags": ["RPC fallback"], "operationId": "genericRpc", "parameters": request_headers, "requestBody": _json_body({"type": "object", "additionalProperties": True}), "responses": {**_response("Frappe method response", {"$ref": "#/components/schemas/FrappeResponse"}), **error}, "x-schema-source": "runtime-generic"}}
    module_names = sorted({dt.module or "Uncategorized" for dt in doctypes})
    for dt in doctypes:
        if dt.name not in typed:
            continue
        if dt.is_child_table:
            continue
        if public_modules and (dt.module or "Uncategorized") not in public_modules:
            continue
        if dt.name in aliases:
            route = aliases[dt.name]
        elif runtime.get("public_module_routes"):
            module_slug = re.sub(r"[^a-z0-9]+", "-", (dt.module or "uncategorized").lower()).strip("-")
            doctype_slug = _resource_slug(dt.name)
            route = f"/api/v1/{module_slug}/{doctype_slug}"
        else:
            route = "/api/resource/" + dt.name.replace(" ", "%20")
        detail_route = route + "/{name}"
        detail_parameters = [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}, *request_headers]
        typed_schema = {"$ref": f"#/components/schemas/{names[dt.name]}"}
        write_schema = _write_schema(schemas[names[dt.name]])
        paths[route] = {
            "get": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"list{names[dt.name]}", "parameters": request_headers, "responses": {**_response("Typed resource list", {"$ref": "#/components/schemas/ResourceListResponse"}), **error}},
            "post": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"create{names[dt.name]}", "parameters": request_headers, "requestBody": _json_body(write_schema), "responses": {**_response("Created typed resource", typed_schema), **error}},
        }
        paths[detail_route] = {
            "get": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"get{names[dt.name]}", "parameters": detail_parameters, "responses": {**_response("Typed resource", typed_schema), **error}},
            "put": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"update{names[dt.name]}", "parameters": detail_parameters, "requestBody": _json_body(write_schema), "responses": {**_response("Updated typed resource", typed_schema), **error}},
            "delete": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"delete{names[dt.name]}", "parameters": detail_parameters, "responses": {**_response("Deleted typed resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}},
        }
        for action in next((item["actions"] for item in runtime.get("document_actions", []) if item["doctype"] == dt.name), []):
            paths[f"{detail_route}/{action}"] = {"post": {"tags": [f"Module: {dt.module or 'Uncategorized'}", "Document actions"], "operationId": f"{action}{names[dt.name]}", "parameters": detail_parameters, "responses": {**_response(f"{action.title()} document", typed_schema), **error}, "x-frappe-action": action}}
    if module_name is None:
        paths["/api/method/upload_file"] = {"post": {"tags": ["Files"], "operationId": "uploadFile", "parameters": request_headers, "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file"], "properties": {"file": {"type": "string", "format": "binary"}, "is_private": {"type": "boolean"}, "doctype": {"type": "string"}, "docname": {"type": "string"}}}}}}, "responses": {**_response("Uploaded file", {"$ref": "#/components/schemas/FileUploadResponse"}), **error}}}
    server = os.environ.get("ERPNEXT_API_URL") or runtime["server_url"]
    if server.startswith("${"):
        server = runtime["server_url"]
    tags = [{"name": "Resource API"}, {"name": "Typed Resource API"}, {"name": "Whitelisted methods"}, {"name": "Metadata"}, {"name": "Files"}, {"name": "RPC fallback"}]
    tags.extend({"name": f"Module: {module}"} for module in module_names if module not in {"Uncategorized"})
    title = f"Letron ERPNext {module_name} API" if module_name else "Letron ERPNext Integration API"
    return {"openapi": runtime["openapi_version"], "info": {"title": title, "version": "0.1.0"}, "servers": [{"url": server}], "tags": tags, "security": [{auth_scheme: []}], "paths": paths, "components": {"securitySchemes": {auth_scheme: {"type": "apiKey", "in": "header", "name": "Authorization"}}, "parameters": {"RequestId": {"name": "X-Request-Id", "in": "header", "required": False, "schema": {"type": "string", "format": "uuid"}}, "IdempotencyKey": {"name": "X-Idempotency-Key", "in": "header", "required": False, "schema": {"type": "string"}}}, "schemas": schemas}, "x-contract": {"runtime": runtime, "transport": contract["transport"], "headers": contract["headers"]}, "x-capabilities": contract.get("capabilities", {}), "x-module": module_name, "x-module-index": {module: sorted(dt.name for dt in doctypes if (dt.module or "Uncategorized") == module) for module in module_names}}
