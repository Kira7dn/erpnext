
import json
import uuid
from threading import Lock
from typing import Any, cast

import frappe

from letron_api.contract_runtime import public_custom_routes, public_route_maps
from letron_api.control.policy import POLICY_DOCTYPES
from letron_api.infrastructure.frappe_compat import install_scheduler_compatibility

install_scheduler_compatibility()

app_name = "letron_api"
app_title = "Letron API"
app_publisher = "Letron"
app_description = "Technical API integration surface for the ERPNext bench"
app_email = "engineering@letron.local"
app_license = "MIT"

# Frappe's native naming-series parser supports application-defined variables.
# The variable is used only by new Letron purchasing records; existing names are
# never renamed.
naming_series_variables = {
    "YYYYMMDD": "letron_api.procurement.naming.parse_yyyymmdd",
}

required_apps = ["frappe", "erpnext"]

_ROUTE_CACHE: dict[tuple[str, str], str] = {}
_ROUTE_CACHE_LOCK = Lock()
PUBLIC_RESOURCE_ROUTES, GENERATED_DOCUMENT_ACTIONS, GENERATED_CUSTOM_ACTIONS = public_route_maps()
GENERATED_CUSTOM_ROUTES = public_custom_routes()
# Shared by route authorization and policy materialization. Dependencies are
# intentionally read-only and never imply create/write/delete permissions.
PUBLIC_PERMISSION_DEPENDENCIES = {
    ("stock", "purchase-receipts"): {"Account"},
}

VIRTUAL_BANKING_ROUTES = {
    ("accounts", "bank-reconciliation", "transactions"): "letron_api.finance.banking.reconciliation_transactions",
    ("accounts", "bank-reconciliation", "balance"): "letron_api.finance.banking.reconciliation_balance",
    ("accounts", "bank-reconciliation", "linked-payments"): "letron_api.finance.banking.reconciliation_linked_payments",
    ("accounts", "bank-reconciliation", "clearance"): "letron_api.finance.banking.reconciliation_update_clearance",
    ("accounts", "bank-reconciliation", "clear-clearance"): "letron_api.finance.banking.reconciliation_clear_clearance",
    ("accounts", "bank-reconciliation", "actions"): "letron_api.finance.banking.reconciliation_action",
    ("accounts", "reports", "report"): "letron_api.finance.banking.report",
    ("accounts", "consolidation", "package"): "letron_api.finance.banking.consolidation_package_report",
    ("accounts", "consolidation", "adjustments"): "letron_api.finance.banking.consolidation_adjustment_create",
    ("accounts", "statement-imports", "details"): "letron_api.finance.banking.statement_details",
    ("accounts", "statement-imports", "update-pdf-tables"): "letron_api.finance.banking.statement_update_pdf_tables",
    ("accounts", "statement-imports", "reextract-pdf-table"): "letron_api.finance.banking.statement_reextract_pdf_table",
    ("accounts", "statement-imports", "set-pdf-table-header"): "letron_api.finance.banking.statement_set_pdf_table_header",
    ("accounts", "statement-imports", "update-column-mapping"): "letron_api.finance.banking.statement_update_column_mapping",
    ("accounts", "statement-imports", "set-header-index"): "letron_api.finance.banking.statement_set_header_index",
}

def _virtual_banking_target(parts: list[str]) -> str | None:
    if len(parts) == 5 and parts[2:5] == ["accounts", "consolidation", "package"]:
        frappe.local.form_dict.update({"filters": frappe.local.request.args.get("filters")})
        return "letron_api.finance.banking.consolidation_package_report"
    if len(parts) == 5 and parts[2:5] == ["accounts", "reports", "report"]:
        frappe.local.form_dict.update({
            "report_key": frappe.local.request.args.get("report_key"),
            "filters": frappe.local.request.args.get("filters"),
        })
        return "letron_api.finance.banking.report"
    if len(parts) == 6 and parts[2:4] == ["accounts", "consolidation"]:
        action = parts[5]
        method = {"submit": "letron_api.finance.banking.consolidation_adjustment_submit", "cancel": "letron_api.finance.banking.consolidation_adjustment_cancel"}.get(action)
        if method:
            frappe.local.form_dict.update({"payload": frappe.request.get_data(as_text=True)})
        return method
    if len(parts) == 4 and parts[2:4] == ["accounts", "statement-imports"]:
        return "letron_api.finance.banking.statement_imports" if frappe.local.request.method == "GET" else "letron_api.finance.banking.statement_import_create"
    if len(parts) == 5:
        if parts[2:4] == ["accounts", "statement-imports"] and parts[4] == "upload":
            return "letron_api.finance.banking.statement_import_upload"
        if parts[2:4] == ["accounts", "statement-imports"]:
            return "letron_api.finance.banking.statement_import_get" if frappe.local.request.method == "GET" else "letron_api.finance.banking.statement_import_update"
        return VIRTUAL_BANKING_ROUTES.get((parts[2], parts[3], parts[4]))
    if len(parts) == 6 and parts[2:4] == ["accounts", "bank-reconciliation"] and parts[4] == "actions":
        frappe.local.form_dict.update({"action": parts[5], "payload": frappe.request.get_data(as_text=True)})
        return "letron_api.finance.banking.reconciliation_action"
    if len(parts) == 6 and parts[2:4] == ["accounts", "statement-imports"]:
        action = parts[5]
        method = {
            "details": "letron_api.finance.banking.statement_details",
            "update-pdf-tables": "letron_api.finance.banking.statement_update_pdf_tables",
            "reextract-pdf-table": "letron_api.finance.banking.statement_reextract_pdf_table",
            "set-pdf-table-header": "letron_api.finance.banking.statement_set_pdf_table_header",
            "update-column-mapping": "letron_api.finance.banking.statement_update_column_mapping",
            "set-header-index": "letron_api.finance.banking.statement_set_header_index",
        }.get(action)
        return method
    return None


def _virtual_asset_target(parts: list[str]) -> str | None:
    if len(parts) == 4 and parts[2:4] == ["assets", "dashboard"]:
        return "letron_api.assets.assets.asset_dashboard"
    if len(parts) == 5 and parts[2:4] == ["assets", "reports"] and parts[4] == "report":
        frappe.local.form_dict.update({
            "report_key": frappe.local.request.args.get("report_key"),
            "filters": frappe.local.request.args.get("filters"),
        })
        return "letron_api.assets.assets.asset_report"
    if len(parts) == 5 and parts[2:4] == ["assets", "actions"]:
        frappe.local.form_dict.update({"action": parts[4], "payload": frappe.request.get_data(as_text=True)})
        return "letron_api.assets.assets.asset_action"
    return None


def _virtual_attachment_target(parts: list[str]) -> str | None:
    if len(parts) == 4 and parts[2:4] == ["files", "attachments"]:
        return "letron_api.delivery.attachments.create_attachment"
    return None


def _virtual_custom_route_target(parts: list[str]) -> str | None:
    """Resolve a generated non-DocType route and expose its path arguments."""

    actual = ["api", "v1", *parts[2:]]
    for route in GENERATED_CUSTOM_ROUTES:
        if route["method"] != frappe.local.request.method.upper():
            continue
        expected = route["path"].strip("/").split("/")
        if len(expected) != len(actual):
            continue
        arguments: dict[str, str] = {}
        matched = True
        for expected_part, actual_part in zip(expected, actual, strict=True):
            if expected_part.startswith("{") and expected_part.endswith("}"):
                arguments[expected_part[1:-1]] = actual_part
            elif expected_part != actual_part:
                matched = False
                break
        if matched:
            frappe.local.form_dict.update(arguments)
            return route["handler"]
    return None



def rewrite_public_routes() -> None:
    """Rewrite public business aliases to native Frappe resource routes."""

    import frappe

    request = frappe.local.request
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    frappe.local.letron_request_id = request_id
    request.environ["LETRON_REQUEST_ID"] = request_id
    path = request.path
    parts = path.strip("/").split("/")
    if len(parts) not in {3, 4, 5, 6} or parts[:2] != ["api", "v1"]:
        return
    frappe.local.letron_public_path = path
    if request.method in {"POST", "PUT", "PATCH"} and request.mimetype == "application/json":
        from letron_api.contract_runtime import validate_request
        try:
            validate_request(request.method, path, request.get_data(cache=True))
        except ValueError as exc:
            frappe.throw(str(exc), exc=frappe.ValidationError)
    target_method = _virtual_attachment_target(parts)
    if target_method:
        if frappe.session.user in {"Guest", ""}:
            frappe.throw("Authentication required", exc=frappe.AuthenticationError)
        request.environ["PATH_INFO"] = f"/api/method/{target_method}"
        request.__dict__["path"] = f"/api/method/{target_method}"
        return
    target_method = _virtual_custom_route_target(parts)
    if target_method:
        if frappe.session.user in {"Guest", ""}:
            frappe.throw("Authentication required", exc=frappe.AuthenticationError)
        target = f"/api/method/{target_method}"
        request.environ["PATH_INFO"] = target
        request.__dict__["path"] = target
        return
    module_slug, doctype_slug = parts[2:4]
    if not module_slug or not doctype_slug:
        return
    if (module_slug, doctype_slug) not in PUBLIC_RESOURCE_ROUTES:
        target_method = _virtual_asset_target(parts) or _virtual_banking_target(parts)
        if target_method:
            if len(parts) >= 5 and parts[2:4] == ["accounts", "statement-imports"]:
                frappe.local.form_dict.setdefault("statement_import_id", parts[4])
            target = f"/api/method/{target_method}"
            request.environ["PATH_INFO"] = target
            request.__dict__["path"] = target
            return
        frappe.throw("Unknown public API route", exc=frappe.DoesNotExistError)
    if frappe.session.user in {"Guest", ""}:
        frappe.throw("Authentication required", exc=frappe.AuthenticationError)
    cache_key = (module_slug, doctype_slug)
    with _ROUTE_CACHE_LOCK:
        doctype = _ROUTE_CACHE.get(cache_key) or PUBLIC_RESOURCE_ROUTES[(module_slug, doctype_slug)]
        _ROUTE_CACHE[cache_key] = doctype
    if not doctype:
        return
    meta = frappe.get_meta(doctype)
    if meta.istable:
        return
    if len(parts) == 6:
        name, action = parts[4:6]
        document_action = action in GENERATED_DOCUMENT_ACTIONS.get((module_slug, doctype_slug), set())
        custom_action = (module_slug, doctype_slug, action) in GENERATED_CUSTOM_ACTIONS
        if not document_action and not custom_action:
            frappe.throw("Unknown public API action", exc=frappe.DoesNotExistError)
        from urllib.parse import urlencode

        target = (
            f"/api/method/{GENERATED_CUSTOM_ACTIONS[(module_slug, doctype_slug, action)]}"
            if custom_action
            else "/api/method/letron_api.control.api.document_action"
        )
        query = urlencode({"doctype": doctype, "name": name, "action": action})
        request.environ["QUERY_STRING"] = query
        # Frappe builds form_dict before running before_request hooks, so also
        # update the parsed arguments when rewriting an already-open request.
        frappe.local.form_dict.update({"doctype": doctype, "name": name, "action": action})
    else:
        if len(parts) == 4 and request.method == "GET":
            target = "/api/method/letron_api.control.api.public_resource_list"
            frappe.local.form_dict.update({"doctype": doctype})
        elif len(parts) == 5:
            target = "/api/method/letron_api.control.api.public_resource_get" if request.method == "GET" else (
                "/api/method/letron_api.control.api.public_resource_update"
                if request.method in {"PUT", "PATCH"}
                else "/api/method/letron_api.control.api.public_resource_delete"
            )
            frappe.local.form_dict.update({"doctype": doctype, "name": parts[4]})
        elif len(parts) == 4 and request.method == "POST":
            target = "/api/method/letron_api.control.api.public_resource_create"
            frappe.local.form_dict.update({"doctype": doctype})
        else:
            frappe.throw("Unsupported public resource operation", exc=frappe.ValidationError)
    # Frappe builds form_dict before before_request hooks.  Keep the public
    # list controls explicit when the alias is rewritten to /api/resource;
    # otherwise some runtime versions fall back to the native default
    # (fields=["name"]) and silently ignore filters/order_by.
    if len(parts) == 4 and request.method == "GET":
        for key in (
            "fields",
            "filters",
            "order_by",
            "limit_page_length",
            "limit_start",
            "as_dict",
            "expand",
        ):
            value = request.args.get(key)
            if value is not None:
                frappe.local.form_dict[key] = value
    request.environ["PATH_INFO"] = target
    request.__dict__["path"] = target

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        idempotency_key = request.headers.get("X-Idempotency-Key")
        if idempotency_key:
            cache_key = f"letron:idempotency:{frappe.local.site}:{frappe.session.user}:{request.method}:{path}:{idempotency_key}"
            cache = cast(Any, frappe.cache)()
            with cache.lock(f"{cache_key}:reservation", timeout=10, blocking_timeout=10):
                if cache.get_value(cache_key, use_local_cache=False):
                    frappe.throw("Duplicate X-Idempotency-Key for this request", exc=frappe.DuplicateEntryError)
                cache.set_value(cache_key, "in-flight", expires_in_sec=86400)
            frappe.local.letron_idempotency_cache_key = cache_key


def add_request_headers(response=None, request=None) -> None:
    """Propagate request IDs and finalize idempotency reservations."""
    if response is None:
        return
    import frappe

    public_path = getattr(frappe.local, "letron_public_path", None)
    if public_path and response.status_code < 400 and response.is_json:
        from letron_api.contract_runtime import validate_response
        try:
            response_value = response.get_json()
            request_method = request.method if request is not None else frappe.local.request.method
            # Native Frappe DELETE responses can be an empty JSON object after
            # the document has already been removed. The public contract uses
            # the standard FrappeResponse envelope, so normalize that native
            # success before validating the generated contract.
            if request_method == "DELETE" and isinstance(response_value, dict):
                response_value.setdefault("message", "ok")
                response.set_data(json.dumps(response_value, ensure_ascii=False))
            validate_response(request_method, public_path, response_value)
        except ValueError as exc:
            frappe.logger("letron_api").error("Public response contract failed: %s", exc)
            response.status_code = 500
            response.set_data(json.dumps({"error": "schema_validation_failed", "message": str(exc)}, ensure_ascii=False))
            response.headers["Content-Type"] = "application/json"

    request_id = getattr(frappe.local, "letron_request_id", None)
    if request_id:
        response.headers["X-Request-Id"] = request_id
    cache_key = getattr(frappe.local, "letron_idempotency_cache_key", None)
    if cache_key:
        cache = cast(Any, frappe.cache)()
        if response.status_code >= 400:
            cache.delete_value(cache_key)
        else:
            cache.set_value(cache_key, "completed", expires_in_sec=86400)


before_request = ["letron_api.auth.gateway.enforce_gateway_ingress", "letron_api.hooks.rewrite_public_routes"]
after_request = ["letron_api.hooks.add_request_headers"]
auth_hooks = []
after_migrate = ["letron_api.procurement.purchase_schema.ensure_schema"]

doc_events = {
    doctype: {
        "after_insert": "letron_api.delivery.delivery.capture_create",
        "on_update": "letron_api.delivery.delivery.capture_update",
        "on_submit": "letron_api.delivery.delivery.capture_submit",
        "on_cancel": "letron_api.delivery.delivery.capture_cancel",
    }
    for doctype in PUBLIC_RESOURCE_ROUTES.values()
}

for policy_doctype in POLICY_DOCTYPES:
    handlers = doc_events.setdefault(policy_doctype, {})
    handlers["validate"] = "letron_api.control.policy.protect_managed_configuration"
    handlers["on_trash"] = "letron_api.control.policy.protect_managed_configuration"

system_settings_handlers = doc_events.setdefault("System Settings", {})
system_settings_handlers["validate"] = "letron_api.control.system_config.protect_system_settings"
system_settings_handlers["on_trash"] = "letron_api.control.system_config.protect_system_settings"

scheduler_events = {
    "all": ["letron_api.delivery.delivery.process_pending_outbox"],
    "hourly": ["letron_api.control.policy.audit", "letron_api.control.system_config.audit"],
    "cron": {
        "*/5 * * * *": [
        ],
        "0 1 * * *": [
            "letron_api.operations.backup.scheduled_s3_backup"
        ]
    },
}
