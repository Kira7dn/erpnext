"""Letron naming-series extensions for new native purchasing records."""

from __future__ import annotations

from typing import Any

import frappe


def parse_yyyymmdd(doc: Any = None, variable: str = "YYYYMMDD") -> str:
    """Return the document business date as YYYYMMDD for Frappe naming series."""

    value = None
    if doc:
        value = doc.get("transaction_date") or doc.get("posting_date") or doc.get("creation")
    parsed = frappe.utils.getdate(value or frappe.utils.nowdate())
    if parsed is None:
        return frappe.utils.nowdate().replace("-", "")
    return parsed.strftime("%Y%m%d")
