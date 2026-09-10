"""Local-only ERP readback helpers for the real integration test.

These functions are invoked through ``bench execute`` by the developer test
script. They are intentionally not whitelisted or exposed as HTTP endpoints.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import frappe


def expire_access(access: str) -> dict[str, Any]:
    """Local-only fixture helper for the expired Magic Link acceptance case."""
    doc = frappe.get_doc("Supplier Portal Access", access)
    doc.magic_expires_at = frappe.utils.now_datetime() - timedelta(seconds=1)
    doc.save(ignore_permissions=True)
    return {"access": doc.name, "status": doc.status, "expired_at": str(doc.magic_expires_at)}


def set_process_deadline(process: str, deadline: str) -> dict[str, Any]:
    """Local-only fixture helper for the MR+3-day scheduler acceptance cases."""
    doc = frappe.get_doc("Supplier Procurement Process", process)
    doc.deadline_at = frappe.utils.get_datetime(deadline)
    doc.save(ignore_permissions=True)
    return {"process": doc.name, "deadline_at": str(doc.deadline_at), "approval_status": doc.approval_status}


def submission_storage(submission: str) -> dict[str, Any]:
    """Return secret-free private-file evidence for an XML submission."""
    doc = frappe.get_doc("Supplier Portal Submission", submission)
    files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Supplier Portal Submission", "attached_to_name": submission},
        fields=["name", "is_private", "file_url", "file_size"],
    )
    return {
        "submission": doc.name,
        "sha256_present": bool(doc.sha256),
        "file_count": len(files),
        "files": [
            {"name": row.name, "is_private": bool(row.is_private), "file_url_is_private": str(row.file_url).startswith("/private/files/"), "file_size": row.file_size}
            for row in files
        ],
    }
