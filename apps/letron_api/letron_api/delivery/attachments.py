"""Shared, permission-checked document attachment endpoint."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint
from frappe.utils.file_manager import save_file

ATTACHABLE_DOCTYPES = frozenset(
    {
        "Supplier",
        "Contact",
        "Address",
        "Item",
        "Material Request",
    }
)
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


def _form_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _request_value(name: str) -> Any:
    value = frappe.form_dict.get(name)
    if value not in (None, ""):
        return value
    return frappe.local.request.args.get(name)


@frappe.whitelist(methods=["POST"])
def create_attachment() -> dict[str, Any]:
    """Upload one private File and attach it to an allowed business document."""

    doctype = str(_request_value("attached_to_doctype") or "").strip()
    docname = str(_request_value("attached_to_name") or "").strip()
    if doctype not in ATTACHABLE_DOCTYPES:
        frappe.throw("Unsupported attachment DocType", exc=frappe.ValidationError)
    if not docname:
        frappe.throw("attached_to_name is required", exc=frappe.ValidationError)

    document = frappe.get_doc(doctype, docname)
    document.check_permission("write")
    uploaded = frappe.request.files.get("file")
    if not uploaded or not uploaded.filename:
        frappe.throw("file is required", exc=frappe.ValidationError)

    content = uploaded.read()
    max_size = cint(frappe.conf.get("max_file_size")) or DEFAULT_MAX_FILE_SIZE
    if len(content) > max_size:
        frappe.throw(f"File exceeds the {max_size} byte limit", exc=frappe.ValidationError)

    file_doc = save_file(
        uploaded.filename,
        content,
        doctype,
        docname,
        is_private=_form_bool(_request_value("is_private"), True),
    )
    return {
        "name": file_doc.name,
        "file_name": file_doc.file_name,
        "file_url": file_doc.file_url,
        "attached_to_doctype": file_doc.attached_to_doctype,
        "attached_to_name": file_doc.attached_to_name,
        "is_private": file_doc.is_private,
    }
