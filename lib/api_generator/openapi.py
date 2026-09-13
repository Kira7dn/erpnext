import hashlib
import copy
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
        # Frappe accepts and returns Check values as either booleans or 0/1.
        schema = {"type": ["boolean", "integer"], "minimum": 0, "maximum": 1}
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


def _replace_model_refs(value: Any, suffix: str) -> Any:
    if isinstance(value, dict):
        result = {key: _replace_model_refs(item, suffix) for key, item in value.items()}
        ref = result.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if not name.endswith(("Response", "Write")):
                result["$ref"] = f"#/components/schemas/{name}{suffix}"
        return result
    if isinstance(value, list):
        return [_replace_model_refs(item, suffix) for item in value]
    return value


def _write_schema(
    schema: dict[str, Any],
    *,
    child_table: bool = False,
    required_overrides: dict[str, dict[str, Any]] | None = None,
    allowed_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    properties = {
        key: _replace_model_refs(copy.deepcopy(value), "Write")
        for key, value in schema["properties"].items()
        if not value.get("readOnly")
    }
    # Public orchestration fields are custom DocFields and are not present in
    # the static DocType model. Keep the write contract closed with an
    # explicit managed overlay instead of accepting arbitrary properties.
    properties.setdefault("custom_letron_orchestration_id", {"type": "string"})
    properties.setdefault("custom_lark_approval_status", {"type": "string"})
    for name, definition in (allowed_overrides or {}).items():
        properties[name] = copy.deepcopy(definition)
    for name, field_schema in properties.items():
        if name == "naming_series" or name.endswith("_series"):
            field_schema = dict(field_schema)
            field_schema.pop("enum", None)
            properties[name] = field_schema
    # Frappe generates `name`; it is a path/output field, never a required
    # public create/update input. Public writes are deliberately closed.
    required = [key for key in schema.get("required", []) if key in properties and key != "name"]
    if child_table:
        # Frappe child rows commonly mark values as required because the
        # controller fills them from the linked Item/UOM after insert. They
        # are not required public inputs (for example MR item uom and
        # conversion_factor), so do not expose storage-time requirements as
        # client payload requirements.
        required = [key for key in required if key not in {"uom", "stock_uom", "conversion_factor"}]
    for name, definition in (required_overrides or {}).items():
        properties[name] = copy.deepcopy(definition)
        if name not in required:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False, "x-module": schema.get("x-module")}


def _response(description: str, schema: dict[str, Any] | None = None, status: str = "200") -> dict[str, Any]:
    response: dict[str, Any] = {"description": description}
    if schema:
        response["content"] = {"application/json": {"schema": schema}}
    return {status: response}


def _document_response(schema: dict[str, Any], envelope: str = "data") -> dict[str, Any]:
    return {"type": "object", "properties": {envelope: schema}, "required": [envelope]}


def _nullable_response_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Allow sparse Frappe list rows to omit or null non-key fields."""
    result: dict[str, Any] = {}
    for name, schema in properties.items():
        if name == "name":
            result[name] = schema
            continue
        if "$ref" in schema:
            result[name] = {"anyOf": [schema, {"type": "null"}]}
            continue
        nullable = dict(schema)
        # Naming series are tenant/configuration data. Frappe may return a
        # configured series that is not present in the DocType's static
        # Select options.
        if name == "naming_series" or name.endswith("_series"):
            nullable.pop("enum", None)
        field_type = nullable.get("type")
        if isinstance(field_type, str):
            accepted_types = [field_type, "null"]
            if field_type == "boolean":
                accepted_types.insert(1, "integer")
                nullable["minimum"] = 0
                nullable["maximum"] = 1
            nullable["type"] = accepted_types
            if isinstance(nullable.get("enum"), list):
                nullable["enum"] = [*nullable["enum"], "", None]
        else:
            nullable = {"anyOf": [schema, {"type": "null"}]}
        result[name] = nullable
    return result


def _read_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Build a sparse native-response schema from a DocType model schema."""
    return {
        "type": "object",
        "properties": _replace_model_refs(_nullable_response_properties(schema["properties"]), "Response"),
        "required": ["name"],
        "additionalProperties": True,
        "x-module": schema.get("x-module"),
    }


def _json_body(schema: dict[str, Any], required: bool = True) -> dict[str, Any]:
    return {"required": required, "content": {"application/json": {"schema": schema}}}


def _example(dt: DocType, write_schema: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field in dt.fields:
        if field.reqd and not field.read_only:
            if field.fieldtype in {"Int", "Long Int", "Float", "Currency", "Percent", "Duration"}:
                values[field.fieldname] = 0
            elif field.fieldtype == "Check":
                values[field.fieldname] = False
            elif field.fieldtype == "Table":
                values[field.fieldname] = []
            else:
                values[field.fieldname] = ""
    return {"example": values, "x-schema-fields": len(write_schema.get("properties", {}))}


def _parameter_schema(parameter: dict[str, Any]) -> dict[str, Any]:
    annotation = (parameter.get("annotation") or "").lower()
    if annotation in {"int", "integer"}:
        return {"type": "integer"}
    if annotation in {"float", "decimal"}:
        return {"type": "number"}
    if annotation in {"bool", "boolean"}:
        return {"type": "boolean"}
    return {"type": "string"}


def _rpc_body(method: WhitelistedMethod) -> tuple[dict[str, Any], str]:
    properties = {item["name"]: _parameter_schema(item) for item in method.parameters}
    required = [item["name"] for item in method.parameters if item.get("required")]
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema, "function-signature"


def _annotate_acceptance(paths: dict[str, Any], contract: dict[str, Any], *, require_all_declared: bool) -> dict[str, int]:
    acceptance = contract.get("acceptance", {})
    default_status = acceptance.get("default_status", "not-tested")
    declared = acceptance.get("operations", {})
    suites = acceptance.get("suites", {})
    default_suite_name = next(iter(suites), None)
    found: set[str] = set()
    summary = {status: 0 for status in ("passed", "partial", "not-tested", "blocked")}
    for path_item in paths.values():
        for verb, operation in path_item.items():
            if verb not in {"get", "post", "put", "patch", "delete"}:
                continue
            operation_id = operation["operationId"]
            result = declared.get(operation_id, {"status": default_status})
            status = result["status"]
            operation["x-test-status"] = status
            summary[status] += 1
            suite_name = result.get("suite", default_suite_name)
            if suite_name and suite_name in suites:
                suite = suites[suite_name]
                operation["x-test-level"] = suite["level"]
                operation["x-test-evidence"] = {"suite": suite_name, "test": suite["test"]}
            if operation_id in declared:
                found.add(operation_id)
                if result.get("note"):
                    operation["x-test-note"] = result["note"]
    unknown = sorted(set(declared) - found)
    if require_all_declared and unknown:
        raise ValueError(f"acceptance contains unknown operationId: {', '.join(unknown)}")
    return summary


def build_openapi(contract: dict[str, Any], doctypes: list[DocType], methods: list[WhitelistedMethod], module_name: str | None = None) -> dict[str, Any]:
    runtime = contract["runtime"]
    auth_scheme = contract.get("auth", {}).get("scheme", "frappeToken")
    names = _schema_names(doctypes)
    public_modules = set(runtime.get("public_modules", []))
    aliases = {item["doctype"]: item["path"] for item in runtime.get("public_resources", [])}
    public_names = set(aliases)
    by_name = {dt.name: dt for dt in doctypes}
    pending = list(public_names)
    while pending:
        current = by_name.get(pending.pop())
        if not current:
            continue
        for field in current.fields:
            if field.fieldtype == "Table" and field.options in by_name and field.options not in public_names:
                public_names.add(field.options)
                pending.append(field.options)
    schemas = {names[dt.name]: _schema(dt, names) for dt in doctypes if dt.name in public_names}
    schemas.update({
        "FrappeResponse": {"type": "object", "properties": {"message": {}}, "required": ["message"]},
        "FrappeError": {"type": "object", "properties": {"exc_type": {"type": "string"}, "exception": {"type": "string"}, "_server_messages": {"type": "string"}, "request_id": {"type": "string"}}},
        "ResourceListResponse": {"type": "object", "properties": {"data": {"type": "array", "items": {"type": "object"}}, "message": {}}},
        "FileUploadResponse": {"type": "object", "properties": {"file_url": {"type": "string"}, "file_name": {"type": "string"}, "message": {}}},
        "PageInfo": {"type": "object", "properties": {"limit_start": {"type": "integer"}, "limit_page_length": {"type": "integer"}}},
        "RuntimeStatus": {"type": "object", "properties": {"ok": {"type": "boolean"}, "status": {"type": "string"}, "version": {"type": "integer"}, "erpnext_version": {"type": "string"}, "sha256": {"type": "string"}, "drift_count": {"type": "integer"}}, "required": ["ok"]},
        "HealthResponse": {"type": "object", "properties": {"message": {"type": "object", "properties": {"ok": {"type": "boolean"}, "app": {"type": "string"}, "site": {"type": "string"}, "frappe_version": {"type": ["string", "null"]}, "installed_apps": {"type": "array", "items": {"type": "string"}}, "bootstrap": {"$ref": "#/components/schemas/RuntimeStatus"}, "config": {"$ref": "#/components/schemas/RuntimeStatus"}, "policy": {"$ref": "#/components/schemas/RuntimeStatus"}, "configuration_bundle": {"$ref": "#/components/schemas/RuntimeStatus"}}, "required": ["ok", "app", "bootstrap", "config", "policy", "configuration_bundle"]}}, "required": ["message"]},
        "BankTransactionAllocation": {"type": "object", "properties": {"payment_document": {"type": "string", "enum": ["Payment Entry", "Journal Entry"]}, "payment_entry": {"type": "string"}, "allocated_amount": {"type": "number", "minimum": 0}}, "required": ["payment_document", "payment_entry"], "additionalProperties": False},
        "BankTransactionReconcileRequest": {"type": "object", "properties": {"allocations": {"type": "array", "items": {"$ref": "#/components/schemas/BankTransactionAllocation"}, "minItems": 1}}, "required": ["allocations"], "additionalProperties": False},
    })
    schemas.update(runtime.get("generated_schemas", {}))
    # Keep model, write-input and sparse-response contracts separate. In
    # particular, child-table inputs must not inherit server-generated fields
    # such as name, stock_uom or conversion_factor as required inputs.
    for dt in doctypes:
        if dt.name not in public_names:
            continue
        model_schema_name = names[dt.name]
        overrides = next(
            (
                item.get("required_write_fields")
                for item in runtime.get("controller_contracts", [])
                if item.get("doctype") == dt.name
            ),
            None,
        )
        allowed_overrides = next(
            (
                item.get("allowed_write_fields")
                for item in runtime.get("controller_contracts", [])
                if item.get("doctype") == dt.name
            ),
            None,
        )
        schemas[f"{model_schema_name}Write"] = _write_schema(
            schemas[model_schema_name],
            child_table=bool(dt.is_child_table),
            required_overrides=overrides,
            allowed_overrides=allowed_overrides,
        )
        schemas[f"{model_schema_name}Response"] = _read_schema(schemas[model_schema_name])
    error_schema = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/FrappeError"}}}}
    error = {
        "400": {"description": "Invalid request", **error_schema},
        "401": {"description": "Authentication required", **error_schema},
        "403": {"description": "Permission denied", **error_schema},
        "404": {"description": "Resource not found", **error_schema},
        "409": {"description": "Idempotency or optimistic concurrency conflict", **error_schema},
        "417": {"description": "Native Frappe validation failure", **error_schema},
        "429": {"description": "Rate limited", **error_schema},
        "500": {"description": "Server or rollback failure", **error_schema},
    }
    request_headers = [{"$ref": "#/components/parameters/RequestId"}]
    write_headers = [*request_headers, {"$ref": "#/components/parameters/IdempotencyKey"}]
    list_parameters = [
        {"name": "fields", "in": "query", "schema": {"type": "string"}, "description": "JSON field-name array"},
        {"name": "filters", "in": "query", "schema": {"type": "string"}, "description": "JSON Frappe filters"},
        {"name": "order_by", "in": "query", "schema": {"type": "string"}},
        {"name": "limit_page_length", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 1000}},
        {"name": "limit_start", "in": "query", "schema": {"type": "integer", "minimum": 0}},
    ]
    paths: dict[str, Any] = {}
    if module_name is None and runtime.get("include_doctype_metadata"):
        paths["/api/method/frappe.desk.form.load.getdoctype"] = {"get": {"tags": ["Metadata"], "operationId": "getDocTypeMetadata", "parameters": [{"name": "doctype", "in": "query", "required": True, "schema": {"type": "string"}}, *request_headers], "responses": {**_response("DocType metadata", {"$ref": "#/components/schemas/FrappeResponse"}), **error}}}
    include = set(runtime.get("include_methods", [])) if runtime.get("include_whitelisted_methods", True) else set()
    for method in methods:
        if module_name is not None:
            continue
        if method.dotted_path not in include:
            continue
        body, source = _rpc_body(method)
        response_schema = {"$ref": "#/components/schemas/HealthResponse"} if method.dotted_path == "letron_api.control.api.health" else {"$ref": "#/components/schemas/FrappeResponse"}
        operation = {"tags": ["Whitelisted methods"], "operationId": method.dotted_path.replace(".", "_"), "parameters": request_headers, "requestBody": _json_body(body, bool(method.parameters)), "responses": {**_response("Frappe method response", response_schema), **error}, "x-source": method.source, "x-schema-source": source}
        if method.allow_guest:
            operation["security"] = []
        verbs = method.methods or ["GET", "POST"]
        path = f"/api/method/{method.dotted_path}"
        paths.setdefault(path, {})
        for verb in verbs:
            paths[path][verb.lower()] = {**operation, "parameters": write_headers if verb.upper() not in {"GET", "HEAD"} else request_headers, "operationId": f"{operation['operationId']}_{verb.lower()}"}
    module_names = sorted({dt.module or "Uncategorized" for dt in doctypes})
    for dt in doctypes:
        if dt.name not in aliases:
            continue
        if dt.is_child_table:
            continue
        if public_modules and (dt.module or "Uncategorized") not in public_modules:
            continue
        route = aliases[dt.name]
        detail_route = route + "/{name}"
        detail_parameters = [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}, *request_headers]
        detail_write_parameters = [{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}, *write_headers]
        model_schema_name = names[dt.name]
        response_schema_name = f"{model_schema_name}Response"
        typed_schema = {"$ref": f"#/components/schemas/{response_schema_name}"}
        write_schema = {"$ref": f"#/components/schemas/{model_schema_name}Write"}
        tag = f"Module: {dt.module or 'Uncategorized'}"
        # Frappe list responses are sparse: callers may request a subset of
        # fields, so DocType-required fields are not response-required here.
        list_item_schema = typed_schema
        list_schema = {"type": "object", "properties": {"data": {"type": "array", "items": list_item_schema}, "message": {}}, "required": ["data"]}
        request_body = _json_body(write_schema)
        request_body["content"]["application/json"]["example"] = _example(dt, write_schema)["example"]
        paths[route] = {
            "get": {"tags": [tag], "summary": f"List {dt.name} records", "description": f"List typed {dt.name} documents.", "operationId": f"list{names[dt.name]}", "parameters": [*request_headers, *list_parameters], "responses": {**_response("Typed resource list", list_schema), **error}, "x-public-operation": "list"},
            "post": {"tags": [tag], "summary": f"Create {dt.name}", "description": f"Create a {dt.name} using the runtime DocType schema.", "operationId": f"create{names[dt.name]}", "parameters": write_headers, "requestBody": request_body, "responses": {**_response("Created typed resource", _document_response(typed_schema)), **error}, "x-public-operation": "create"},
        }
        paths[detail_route] = {
            "get": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"get{names[dt.name]}", "parameters": detail_parameters, "responses": {**_response("Typed resource", _document_response(typed_schema)), **error}, "x-public-operation": "read"},
            "put": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"update{names[dt.name]}", "parameters": detail_write_parameters, "requestBody": _json_body(write_schema), "responses": {**_response("Updated typed resource", _document_response(typed_schema)), **error}, "x-public-operation": "update"},
            "delete": {"tags": [f"Module: {dt.module or 'Uncategorized'}"], "operationId": f"delete{names[dt.name]}", "parameters": detail_write_parameters, "responses": {**_response("Deleted typed resource", {"$ref": "#/components/schemas/FrappeResponse"}), **error}, "x-public-operation": "delete"},
        }
        for action in next((item["actions"] for item in runtime.get("document_actions", []) if item["doctype"] == dt.name), []):
            paths[f"{detail_route}/{action}"] = {"post": {"tags": [f"Module: {dt.module or 'Uncategorized'}", "Document actions"], "operationId": f"{action}{names[dt.name]}", "parameters": detail_write_parameters, "responses": {**_response(f"{action.title()} document", _document_response(typed_schema, "message")), **error}, "x-frappe-action": action, "x-public-operation": "update" if action == "submit" else "delete"}}
        for custom in runtime.get("custom_actions", []):
            if custom["doctype"] != dt.name:
                continue
            action_path = f"{detail_route}/{custom['path_suffix']}"
            action_body_spec = custom.get("request_schema", {"type": "object", "additionalProperties": False})
            action_body = (
                {"$ref": f"#/components/schemas/{action_body_spec}"}
                if isinstance(action_body_spec, str)
                else copy.deepcopy(action_body_spec)
            )
            response_spec = custom.get("response_schema", f"{names[dt.name]}Response")
            response_schema = (
                {"$ref": f"#/components/schemas/{response_spec}"}
                if isinstance(response_spec, str)
                else copy.deepcopy(response_spec)
            )
            response_envelope = custom.get("response_envelope", "data")
            paths[action_path] = {
                "post": {
                    "tags": [f"Module: {dt.module or 'Uncategorized'}", "Business actions"],
                    "summary": f"{custom['action'].title()} {dt.name}",
                    "operationId": custom["operation_id"],
                    "parameters": detail_write_parameters,
                    "requestBody": _json_body(action_body),
                    "responses": {
                        **_response(
                            f"{custom['action'].title()} {dt.name}",
                            _document_response(response_schema, response_envelope),
                        ),
                        **error,
                    },
                    "x-frappe-handler": custom["handler"],
                    "x-native-action": custom["action"],
                    "x-public-operation": "update",
                }
            }
    for custom in runtime.get("custom_routes", []):
        if module_name is not None and custom["module"] != module_name:
            continue
        method = custom["method"].lower()
        parameters = []
        for name in re.findall(r"\{([^}]+)\}", custom["path"]):
            parameters.append({"name": name, "in": "path", "required": True, "schema": {"type": "string"}})
        parameters.extend(write_headers if method not in {"get", "head"} else request_headers)
        operation: dict[str, Any] = {
            "tags": [f"Module: {custom['module']}", "Business routes"],
            "summary": custom.get("summary", custom["operation_id"]),
            "operationId": custom["operation_id"],
            "parameters": parameters,
            "responses": {**_response(custom.get("response_description", "Business route response"), {"$ref": "#/components/schemas/FrappeResponse"}), **error},
            "x-frappe-handler": custom["handler"],
            "x-public-operation": custom["operation"],
        }
        if method not in {"get", "head"}:
            if custom.get("content_type") == "multipart/form-data":
                properties = {"file": {"type": "string", "format": "binary"}}
                for field in custom.get("multipart_fields", []):
                    properties[field] = {"type": "string"}
                operation["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object", "required": ["file", *custom.get("required_multipart_fields", [])], "properties": properties}}}}
            else:
                operation["requestBody"] = _json_body({"type": "object", "additionalProperties": True}, required=False)
        paths.setdefault(custom["path"], {})[method] = operation
    server = os.environ.get("ERPNEXT_API_URL") or runtime["server_url"]
    if server.startswith("${"):
        server = runtime["server_url"]
    tags = [{"name": "Typed Resource API"}, {"name": "Whitelisted methods"}, {"name": "Metadata"}, {"name": "Files"}]
    tags.extend({"name": f"Module: {module}"} for module in module_names if module not in {"Uncategorized"})
    title = f"Letron ERPNext {module_name} API" if module_name else "Letron ERPNext Integration API"
    security_scheme = {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": "Frappe token authentication: token api_key:api_secret",
    }
    acceptance_summary = _annotate_acceptance(paths, contract, require_all_declared=module_name is None)
    return {"openapi": runtime["openapi_version"], "info": {"title": title, "version": "0.1.0"}, "servers": [{"url": server}], "tags": tags, "security": [{auth_scheme: []}], "paths": paths, "components": {"securitySchemes": {auth_scheme: security_scheme}, "parameters": {"RequestId": {"name": "X-Request-Id", "in": "header", "required": False, "schema": {"type": "string", "format": "uuid"}}, "IdempotencyKey": {"name": "X-Idempotency-Key", "in": "header", "required": False, "schema": {"type": "string"}}}, "schemas": schemas}, "x-contract": {"runtime": runtime, "transport": contract["transport"], "headers": contract["headers"]}, "x-capabilities": contract.get("capabilities", {}), "x-acceptance-summary": acceptance_summary, "x-module": module_name, "x-module-index": {module: sorted(dt.name for dt in doctypes if (dt.module or "Uncategorized") == module) for module in module_names}}
