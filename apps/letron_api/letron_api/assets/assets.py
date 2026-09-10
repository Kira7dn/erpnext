"""Typed fixed-asset adapters for the Next.js Assets workspace.

Only native ERPNext methods explicitly listed below are exposed.  The adapter
must never become a generic ``frappe.get_attr`` endpoint.
"""

from __future__ import annotations

from typing import Any, cast

import frappe


ASSET_ACTIONS = {
    "make-asset-movement": "erpnext.assets.doctype.asset.asset.make_asset_movement",
    "make-journal-entry": "erpnext.assets.doctype.asset.asset.make_journal_entry",
    "create-asset-maintenance": "erpnext.assets.doctype.asset.asset.create_asset_maintenance",
    "create-asset-repair": "erpnext.assets.doctype.asset.asset.create_asset_repair",
    "create-asset-capitalization": "erpnext.assets.doctype.asset.asset.create_asset_capitalization",
    "make-sales-invoice": "erpnext.assets.doctype.asset.asset.make_sales_invoice",
    "split-asset": "erpnext.assets.doctype.asset.asset.split_asset",
    "create-value-adjustment": "erpnext.assets.doctype.asset.asset.create_asset_value_adjustment",
    "get-purchase-doc-values": "erpnext.assets.doctype.asset.asset.get_values_from_purchase_doc",
    "get-depreciation-rate": "erpnext.assets.doctype.asset.asset.get_depreciation_rate",
    "scrap-asset": "erpnext.assets.doctype.asset.depreciation.scrap_asset",
    "restore-asset": "erpnext.assets.doctype.asset.depreciation.restore_asset",
    "has-active-capitalization": "erpnext.assets.doctype.asset.asset.has_active_capitalization",
    "get-asset-depreciation-schedule": "erpnext.assets.doctype.asset_depreciation_schedule.asset_depreciation_schedule.get_asset_depr_schedule_doc",
    "get-asset-item-details": "erpnext.assets.doctype.asset.asset.get_item_details",
    "get-capitalization-items": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_items_tagged_to_wip_composite_asset",
    "get-capitalization-target-item": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_target_item_details",
    "get-capitalization-target-asset": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_target_asset_details",
    "get-consumed-stock-item-details": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_consumed_stock_item_details",
    "get-consumed-asset-details": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_consumed_asset_details",
    "get-service-item-details": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_service_item_details",
    "get-warehouse-details": "erpnext.assets.doctype.asset_capitalization.asset_capitalization.get_warehouse_details",
    "get-maintenance-log": "erpnext.assets.doctype.asset_maintenance.asset_maintenance.get_maintenance_log",
    "calculate-next-due-date": "erpnext.assets.doctype.asset_maintenance.asset_maintenance.calculate_next_due_date",
    "get-asset-value-after-depreciation": "erpnext.assets.doctype.asset.asset.get_asset_value_after_depreciation",
    "get-accounting-dimensions": "erpnext.assets.doctype.asset_value_adjustment.asset_value_adjustment.get_value_of_accounting_dimensions",
    "get-repair-downtime": "erpnext.assets.doctype.asset_repair.asset_repair.get_downtime",
    "get-unallocated-repair-cost": "erpnext.assets.doctype.asset_repair.asset_repair.get_unallocated_repair_cost",
    "make-depreciation-entry": "erpnext.assets.doctype.asset.depreciation.make_depreciation_entry",
}


def _asset_instance_action(action: str, payload: dict[str, Any]) -> Any:
    asset_name = payload.get("asset") or payload.get("asset_name")
    if not asset_name:
        frappe.throw(f"{action} requires asset or asset_name", exc=frappe.ValidationError)
    asset_name = str(asset_name)
    asset = cast(Any, frappe.get_doc("Asset", asset_name))
    asset.check_permission("read")
    if action == "get-manual-depreciation-entries":
        return asset.get_manual_depreciation_entries()
    frappe.throw("Unsupported asset instance action", exc=frappe.ValidationError)


INSTANCE_ACTIONS = {"get-manual-depreciation-entries"}

REPORTS = {
    "fixed-asset-register": "Fixed Asset Register",
    "asset-depreciation-ledger": "Asset Depreciation Ledger",
    "asset-depreciations-and-balances": "Asset Depreciations and Balances",
    "asset-maintenance": "Asset Maintenance",
    "asset-activity": "Asset Activity",
}


def _json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except (TypeError, ValueError):
            return value
    return value


def _payload(payload: Any = None) -> dict[str, Any]:
    value = _json(payload, {})
    if not isinstance(value, dict):
        frappe.throw("payload must be an object", exc=frappe.ValidationError)
    return value


@frappe.whitelist(methods=["POST"])
def asset_action(action: str, payload: Any = None) -> Any:
    arguments = _payload(payload)
    if action in INSTANCE_ACTIONS:
        return _asset_instance_action(action, arguments)
    method_path = ASSET_ACTIONS.get(action)
    if not method_path:
        frappe.throw("Unsupported asset action", exc=frappe.ValidationError)
    return frappe.get_attr(str(method_path))(**arguments)


@frappe.whitelist(methods=["GET"])
def asset_report(report_key: str | None = None, filters: Any = None) -> Any:
    report_key = report_key or frappe.form_dict.get("report_key")
    filters = filters if filters is not None else frappe.form_dict.get("filters")
    report_name = REPORTS.get(str(report_key) if report_key else "")
    if not report_name:
        frappe.throw("Unsupported asset report", exc=frappe.ValidationError)
    frappe.has_permission("Asset", "read", throw=True)
    from frappe.desk.query_report import run

    return run(report_name=report_name, filters=_payload(filters), ignore_prepared_report=True)


@frappe.whitelist(methods=["GET"])
def asset_dashboard() -> dict[str, Any]:
    frappe.has_permission("Asset", "read", throw=True)
    counts = {
        "total": frappe.db.count("Asset"),
        "active": frappe.db.count("Asset", {"status": "Submitted"}),
        "draft": frappe.db.count("Asset", {"status": "Draft"}),
        "scrapped": frappe.db.count("Asset", {"status": "Scrapped"}),
    }
    return {"counts": counts}
