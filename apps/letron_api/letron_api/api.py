"""Non-business health and runtime endpoints for the Letron ERPNext app."""

from __future__ import annotations

import frappe


def _runtime_info() -> dict[str, object]:
    installed_apps = frappe.get_installed_apps()
    return {
        "site": frappe.local.site,
        "frappe_version": getattr(frappe, "__version__", None),
        "installed_apps": installed_apps,
    }


@frappe.whitelist(allow_guest=True)
def health() -> dict[str, object]:
    """Return a lightweight authenticated application health response."""

    return {"ok": True, "app": "letron_api", **_runtime_info()}


@frappe.whitelist()
def runtime_info() -> dict[str, object]:
    """Return runtime metadata used by Phase 1 verification tooling."""

    return _runtime_info()
