import frappe
from frappe.model.document import Document


class LetronSSOAuditLog(Document):
    def validate(self) -> None:
        if not self.is_new():
            frappe.throw("Letron SSO Audit Log is immutable", exc=frappe.PermissionError)
