
import uuid
from threading import Lock
from typing import Any, cast

import frappe

from letron_api.frappe_compat import install_scheduler_compatibility
from letron_api.policy import POLICY_DOCTYPES

install_scheduler_compatibility()

app_name = "letron_api"
app_title = "Letron API"
app_publisher = "Letron"
app_description = "Technical API integration surface for the ERPNext bench"
app_email = "engineering@letron.local"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

_ROUTE_CACHE: dict[tuple[str, str], str] = {}
_ROUTE_CACHE_LOCK = Lock()
PUBLIC_RESOURCE_ROUTES = {
    ("assets", "assets"): "Asset",
    ("assets", "asset-categories"): "Asset Category",
    ("assets", "asset-capitalizations"): "Asset Capitalization",
    ("assets", "asset-maintenance"): "Asset Maintenance",
    ("assets", "asset-movements"): "Asset Movement",
    ("assets", "asset-repairs"): "Asset Repair",
    ("assets", "asset-value-adjustments"): "Asset Value Adjustment",
    ("assets", "asset-maintenance-teams"): "Asset Maintenance Team",
    ("assets", "asset-maintenance-logs"): "Asset Maintenance Log",
    ("assets", "asset-depreciation-schedules"): "Asset Depreciation Schedule",
    ("assets", "asset-shift-factors"): "Asset Shift Factor",
    ("assets", "asset-shift-allocations"): "Asset Shift Allocation",
    ("assets", "locations"): "Location",
    ("selling", "customers"): "Customer",
    ("selling", "quotations"): "Quotation",
    ("selling", "sales-orders"): "Sales Order",
    ("selling", "delivery-notes"): "Delivery Note",
    ("crm", "leads"): "Lead",
    ("crm", "opportunities"): "Opportunity",
    ("crm", "request-for-quotations"): "Request for Quotation",
    ("crm", "supplier-quotations"): "Supplier Quotation",
    ("accounts", "sales-invoices"): "Sales Invoice",
    ("accounts", "purchase-invoices"): "Purchase Invoice",
    ("accounts", "payment-entries"): "Payment Entry",
    ("accounts", "banks"): "Bank",
    ("accounts", "bank-accounts"): "Bank Account",
    ("accounts", "modes-of-payment"): "Mode of Payment",
    ("accounts", "cost-centers"): "Cost Center",
    ("accounts", "journal-entries"): "Journal Entry",
    ("accounts", "payment-requests"): "Payment Request",
    ("accounts", "bank-transactions"): "Bank Transaction",
    ("accounts", "payment-orders"): "Payment Order",
    ("accounts", "bank-transaction-rules"): "Bank Transaction Rule",
    ("buying", "suppliers"): "Supplier",
    ("buying", "purchase-orders"): "Purchase Order",
    ("stock", "items"): "Item",
    ("stock", "warehouses"): "Warehouse",
    ("contacts", "addresses"): "Address",
    ("contacts", "contacts"): "Contact",
    ("stock", "material-requests"): "Material Request",
    ("stock", "purchase-receipts"): "Purchase Receipt",
    ("stock", "stock-entries"): "Stock Entry",
    ("stock", "item-prices"): "Item Price",
    ("stock", "stock-reconciliations"): "Stock Reconciliation",
    ("stock", "serial-nos"): "Serial No",
    ("stock", "batches"): "Batch",
    ("stock", "quality-inspections"): "Quality Inspection",
    ("stock", "pick-lists"): "Pick List",
    ("stock", "shipments"): "Shipment",
    ("stock", "landed-cost-vouchers"): "Landed Cost Voucher",
    ("stock", "stock-reservation-entries"): "Stock Reservation Entry",
}
DOCUMENT_ACTIONS = {
    ("assets", "assets"): {"submit", "cancel"},
    ("assets", "asset-capitalizations"): {"submit", "cancel"},
    ("assets", "asset-movements"): {"submit", "cancel"},
    ("assets", "asset-repairs"): {"submit", "cancel"},
    ("assets", "asset-value-adjustments"): {"submit", "cancel"},
    ("accounts", "sales-invoices"): {"submit", "cancel"},
    ("accounts", "purchase-invoices"): {"submit", "cancel"},
    ("selling", "sales-orders"): {"submit", "cancel"},
    ("buying", "purchase-orders"): {"submit", "cancel"},
    ("stock", "material-requests"): {"submit", "cancel"},
    ("stock", "purchase-receipts"): {"submit", "cancel"},
    ("stock", "stock-entries"): {"submit", "cancel"},
    ("accounts", "journal-entries"): {"submit", "cancel"},
    ("accounts", "payment-requests"): {"submit", "cancel"},
    ("accounts", "payment-orders"): {"submit", "cancel"},
    ("accounts", "payment-entries"): {"submit", "cancel"},
    ("accounts", "bank-transactions"): {"submit", "cancel"},
}
CUSTOM_ACTIONS = {
    ("accounts", "bank-transactions", "reconcile"): "letron_api.accounts_reconciliation.reconcile_bank_transaction",
    ("accounts", "bank-transactions", "unreconcile"): "letron_api.accounts_reconciliation.unreconcile_bank_transaction",
    ("accounts", "bank-transaction-rules", "run-evaluation"): "letron_api.banking.run_rule_evaluation",
}

VIRTUAL_BANKING_ROUTES = {
    ("accounts", "bank-reconciliation", "transactions"): "letron_api.banking.reconciliation_transactions",
    ("accounts", "bank-reconciliation", "balance"): "letron_api.banking.reconciliation_balance",
    ("accounts", "bank-reconciliation", "linked-payments"): "letron_api.banking.reconciliation_linked_payments",
    ("accounts", "bank-reconciliation", "clearance"): "letron_api.banking.reconciliation_update_clearance",
    ("accounts", "bank-reconciliation", "clear-clearance"): "letron_api.banking.reconciliation_clear_clearance",
    ("accounts", "bank-reconciliation", "actions"): "letron_api.banking.reconciliation_action",
    ("accounts", "reports", "report"): "letron_api.banking.report",
    ("accounts", "statement-imports", "details"): "letron_api.banking.statement_details",
    ("accounts", "statement-imports", "update-pdf-tables"): "letron_api.banking.statement_update_pdf_tables",
    ("accounts", "statement-imports", "reextract-pdf-table"): "letron_api.banking.statement_reextract_pdf_table",
    ("accounts", "statement-imports", "set-pdf-table-header"): "letron_api.banking.statement_set_pdf_table_header",
    ("accounts", "statement-imports", "update-column-mapping"): "letron_api.banking.statement_update_column_mapping",
    ("accounts", "statement-imports", "set-header-index"): "letron_api.banking.statement_set_header_index",
}

def _virtual_banking_target(parts: list[str]) -> str | None:
    if len(parts) == 4 and parts[2:4] == ["accounts", "statement-imports"]:
        return "letron_api.banking.statement_imports" if frappe.local.request.method == "GET" else "letron_api.banking.statement_import_create"
    if len(parts) == 4 and parts[2:4] == ["accounts", "settings"]:
        return "letron_api.banking.accounts_settings" if frappe.local.request.method == "GET" else "letron_api.banking.accounts_settings_update"
    if len(parts) == 5:
        if parts[2:4] == ["accounts", "statement-imports"] and parts[4] == "upload":
            return "letron_api.banking.statement_import_upload"
        if parts[2:4] == ["accounts", "statement-imports"]:
            return "letron_api.banking.statement_import_get" if frappe.local.request.method == "GET" else "letron_api.banking.statement_import_update"
        return VIRTUAL_BANKING_ROUTES.get((parts[2], parts[3], parts[4]))
    if len(parts) == 6 and parts[2:4] == ["accounts", "bank-reconciliation"] and parts[4] == "actions":
        frappe.local.form_dict.update({"action": parts[5], "payload": frappe.request.get_data(as_text=True)})
        return "letron_api.banking.reconciliation_action"
    if len(parts) == 6 and parts[2:4] == ["accounts", "statement-imports"]:
        action = parts[5]
        method = {
            "details": "letron_api.banking.statement_details",
            "update-pdf-tables": "letron_api.banking.statement_update_pdf_tables",
            "reextract-pdf-table": "letron_api.banking.statement_reextract_pdf_table",
            "set-pdf-table-header": "letron_api.banking.statement_set_pdf_table_header",
            "update-column-mapping": "letron_api.banking.statement_update_column_mapping",
            "set-header-index": "letron_api.banking.statement_set_header_index",
        }.get(action)
        return method
    return None


def _virtual_asset_target(parts: list[str]) -> str | None:
    if len(parts) == 4 and parts[2:4] == ["assets", "dashboard"]:
        return "letron_api.assets.asset_dashboard"
    if len(parts) == 5 and parts[2:4] == ["assets", "reports"] and parts[4] == "report":
        frappe.local.form_dict.update({
            "report_key": frappe.local.request.args.get("report_key"),
            "filters": frappe.local.request.args.get("filters"),
        })
        return "letron_api.assets.asset_report"
    if len(parts) == 5 and parts[2:4] == ["assets", "actions"]:
        frappe.local.form_dict.update({"action": parts[4], "payload": frappe.request.get_data(as_text=True)})
        return "letron_api.assets.asset_action"
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
    if len(parts) not in {4, 5, 6} or parts[:2] != ["api", "v1"]:
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
        return
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
        document_action = action in DOCUMENT_ACTIONS.get((module_slug, doctype_slug), set())
        custom_action = (module_slug, doctype_slug, action) in CUSTOM_ACTIONS
        if not document_action and not custom_action:
            return
        from urllib.parse import urlencode

        target = (
            f"/api/method/{CUSTOM_ACTIONS[(module_slug, doctype_slug, action)]}"
            if custom_action
            else "/api/method/letron_api.api.document_action"
        )
        query = urlencode({"doctype": doctype, "name": name, "action": action})
        request.environ["QUERY_STRING"] = query
        # Frappe builds form_dict before running before_request hooks, so also
        # update the parsed arguments when rewriting an already-open request.
        frappe.local.form_dict.update({"doctype": doctype, "name": name, "action": action})
    else:
        target = f"/api/resource/{doctype}"
        if len(parts) == 5:
            # PATH_INFO follows WSGI's latin-1 transport convention. Preserve
            # the original UTF-8 bytes so Frappe's router decodes the name once.
            name = parts[4].encode("utf-8").decode("latin-1")
            target += f"/{name}"
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


before_request = ["letron_api.gateway.enforce_gateway_ingress", "letron_api.hooks.rewrite_public_routes"]
after_request = ["letron_api.hooks.add_request_headers"]
auth_hooks = []

doc_events = {
    doctype: {
        "after_insert": "letron_api.delivery.capture_create",
        "on_update": "letron_api.delivery.capture_update",
        "on_submit": "letron_api.delivery.capture_submit",
        "on_cancel": "letron_api.delivery.capture_cancel",
    }
    for doctype in PUBLIC_RESOURCE_ROUTES.values()
}

for policy_doctype in POLICY_DOCTYPES:
    handlers = doc_events.setdefault(policy_doctype, {})
    handlers["validate"] = "letron_api.policy.protect_managed_configuration"
    handlers["on_trash"] = "letron_api.policy.protect_managed_configuration"

system_settings_handlers = doc_events.setdefault("System Settings", {})
system_settings_handlers["validate"] = "letron_api.system_config.protect_system_settings"
system_settings_handlers["on_trash"] = "letron_api.system_config.protect_system_settings"

user_handlers = doc_events.setdefault("User", {})
user_handlers["validate"] = "letron_api.sso_identity.protect_lark_managed_user"

scheduler_events = {
    "all": ["letron_api.delivery.process_pending_outbox"],
    "hourly": ["letron_api.policy.audit", "letron_api.system_config.audit"],
    "cron": {
        "0 1 * * *": [
            "letron_api.backup.scheduled_s3_backup"
        ]
    },
}
