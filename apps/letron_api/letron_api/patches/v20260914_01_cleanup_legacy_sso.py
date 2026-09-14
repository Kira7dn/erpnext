"""Remove retired ERP role-sync and break-glass columns."""

from __future__ import annotations

import frappe

_RETIRED_FIELDS = {
    "Letron SSO Identity": (
        "group_ids",
        "gateway_roles_fingerprint",
        "gateway_policy_version",
        "gateway_synced_at",
        "disabled_by_sync",
        "local_blocked",
        "break_glass_until",
        "break_glass_reason",
        "sync_state",
        "last_error",
    ),
    "Letron SSO Audit Log": ("before_roles", "after_roles"),
}


def execute() -> None:
    if frappe.db.table_exists("Letron SSO Identity") and frappe.db.has_column("Letron SSO Identity", "last_sync_at"):
        if not frappe.db.has_column("Letron SSO Identity", "provisioned_at"):
            frappe.db.sql_ddl(
                "ALTER TABLE `tabLetron SSO Identity` ADD COLUMN `provisioned_at` datetime(6) NULL"
            )
            frappe.db.sql(
                "UPDATE `tabLetron SSO Identity` SET `provisioned_at` = `last_sync_at` WHERE `provisioned_at` IS NULL"
            )
        frappe.db.sql_ddl("ALTER TABLE `tabLetron SSO Identity` DROP COLUMN `last_sync_at`")
        frappe.db.delete("DocField", {"parent": "Letron SSO Identity", "fieldname": "last_sync_at"})

    for doctype, fields in _RETIRED_FIELDS.items():
        if not frappe.db.table_exists(doctype):
            continue
        table = f"tab{doctype}"
        for field in fields:
            if frappe.db.has_column(doctype, field):
                frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{field}`")
            frappe.db.delete("DocField", {"parent": doctype, "fieldname": field})
        frappe.reload_doc("letron_api", "doctype", frappe.scrub(doctype), force=True)
        frappe.clear_cache(doctype=doctype)
