import json
from typing import Any

import frappe
from frappe.model.document import Document


class LetronVASReportPackage(Document):
    """Immutable, policy-versioned statutory report package."""

    _TRANSITIONS = {
        "Draft": {"Draft", "Review", "Rejected"},
        "Review": {"Review", "Closed", "Rejected"},
        "Closed": {"Closed", "Issued"},
        "Rejected": {"Rejected", "Draft"},
        "Issued": {"Issued"},
    }

    def validate(self) -> None:
        document: Any = self
        status = str(document.status or "Draft")
        previous = self.get_db_value("status") if not self.is_new() else None
        if status not in self._TRANSITIONS:
            frappe.throw("Unsupported VAS report package status", exc=frappe.ValidationError)
        if previous and status not in self._TRANSITIONS.get(str(previous), set()):
            frappe.throw("Invalid VAS report package status transition", exc=frappe.ValidationError)
        if previous in {"Closed", "Issued"} and not (previous == "Closed" and status == "Issued"):
            frappe.throw("Closed or issued VAS report packages are immutable", exc=frappe.PermissionError)
        if document.from_date and document.to_date and str(document.from_date) > str(document.to_date):
            frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
        unresolved = []
        for note in document.get("notes") or []:
            if note.get("accounting_input") and str(note.get("status")) != "derived":
                note.status = "derived"
                note.data_json = str(note.accounting_input)
            if str(note.get("status") or "") != "derived":
                unresolved.append(str(note.get("code") or ""))
        try:
            previous_validation = json.loads(str(document.validation_json or "{}"))
        except json.JSONDecodeError:
            previous_validation = {}
        statement_ok = previous_validation.get("statement_ok", True) is True
        if status in {"Closed", "Issued"} and unresolved:
            frappe.throw(
                "VAS report package has unresolved disclosure notes: " + ", ".join(unresolved),
                exc=frappe.ValidationError,
            )
        document.validation_json = json.dumps(
            {
                "ok": not unresolved and statement_ok,
                "statement_ok": statement_ok,
                "unresolved": unresolved,
                "reconciliation_checks": [],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if status == "Issued":
            try:
                validation = json.loads(str(document.validation_json or "{}"))
            except json.JSONDecodeError as exc:
                frappe.throw("VAS report package validation JSON is invalid", exc=frappe.ValidationError)
                raise exc
            if validation.get("ok") is not True:
                frappe.throw("Only a valid VAS report package can be issued", exc=frappe.ValidationError)

    def before_submit(self) -> None:
        document: Any = self
        if str(document.status) != "Issued":
            frappe.throw("VAS report package must be Issued before submit", exc=frappe.ValidationError)
        self.issued_by = frappe.session.user
        self.issued_at = frappe.utils.now_datetime()

    def on_update_after_submit(self) -> None:
        frappe.throw("Issued VAS report packages are immutable", exc=frappe.PermissionError)

    def before_cancel(self) -> None:
        frappe.throw("Issued VAS report packages cannot be cancelled", exc=frappe.PermissionError)
