"""Local-only ERP readback helpers for the real integration test.

These functions are invoked through ``bench execute`` by the developer test
script. They are intentionally not whitelisted or exposed as HTTP endpoints.
"""

from __future__ import annotations

from typing import Any

import frappe


def email_delivery_status() -> dict[str, Any]:
    """Return a secret-free legacy SMTP diagnostic; Lark Mail is tested by the TS runner."""
    if not frappe.db.table_exists("Email Account"):
        return {"ready": False, "reason": "Email Account table is unavailable"}

    rows = frappe.get_all(
        "Email Account",
        filters={"enable_outgoing": 1},
        fields=["name", "email_id", "default_outgoing", "smtp_server", "smtp_port"],
        order_by="default_outgoing desc, modified desc",
        limit_page_length=20,
    )
    usable = [
        row for row in rows
        if row.get("smtp_server") and row.get("email_id")
    ]
    default = next((row for row in usable if row.get("default_outgoing")), None)
    selected = default or (usable[0] if usable else None)
    if not selected:
        return {
            "ready": False,
            "reason": "No enabled outgoing Email Account with SMTP server is configured",
            "enabled_outgoing_accounts": len(rows),
        }
    return {
        "ready": True,
        "account": selected.name,
        "sender_domain": str(selected.email_id).split("@", 1)[-1],
        "smtp_port": selected.smtp_port,
    }


def latest_emails(subject: str, after: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Read legacy ERP mail records only; the supplier flow uses Lark Mail readback."""
    filters: dict[str, Any] = {"subject": subject}
    if after:
        filters["creation"] = [">=", after]
    return frappe.get_all(
        "Email Queue",
        filters=filters,
        fields=["name", "subject", "recipients", "message", "creation"],
        order_by="creation desc",
        limit_page_length=limit,
    )
