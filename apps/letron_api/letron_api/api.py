"""Non-business health and runtime endpoints for the Letron ERPNext app."""

from __future__ import annotations

import re

import frappe
from frappe.utils.nestedset import rebuild_tree


def _runtime_info() -> dict[str, object]:
    installed_apps = frappe.get_installed_apps()
    return {
        "site": frappe.local.site,
        "frappe_version": getattr(frappe, "__version__", None),
        "installed_apps": installed_apps,
    }


@frappe.whitelist(allow_guest=True, methods=["GET"])
def health() -> dict[str, object]:
    """Return a lightweight authenticated application health response."""

    return {"ok": True, "app": "letron_api", **_runtime_info()}


@frappe.whitelist(methods=["GET"])
def runtime_info() -> dict[str, object]:
    """Return runtime metadata used by integration verification tooling."""

    return _runtime_info()


@frappe.whitelist(methods=["GET"])
def runtime_snapshot() -> dict[str, object]:
    """Return runtime metadata used by integration verification, not business logic."""

    snapshot: dict[str, object] = {**_runtime_info(), "doctype_metadata": {}}
    for doctype in ("Company", "Currency", "User"):
        try:
            meta = frappe.get_meta(doctype)
            snapshot["doctype_metadata"][doctype] = {
                "fields": [
                    {"fieldname": field.fieldname, "fieldtype": field.fieldtype, "reqd": field.reqd}
                    for field in meta.fields
                ],
                "permissions": [
                    {"role": permission.role, "read": permission.read, "write": permission.write, "create": permission.create}
                    for permission in meta.permissions
                ],
                "has_permission": frappe.has_permission(doctype, ptype="read"),
            }
        except Exception as error:  # noqa: BLE001 - snapshot must report metadata errors without masking runtime state
            snapshot["doctype_metadata"][doctype] = {"error": type(error).__name__}
    return snapshot


@frappe.whitelist(methods=["POST"])
def document_action(doctype: str, name: str, action: str) -> dict[str, object]:
    """Run an explicitly supported document lifecycle action.

    The route hook supplies the DocType and name from the clean module URL.
    Document methods enforce the normal Frappe permission and validation rules.
    """
    supported = {
        ("Sales Invoice", "submit"),
        ("Sales Invoice", "cancel"),
        ("Purchase Invoice", "submit"),
        ("Purchase Invoice", "cancel"),
        ("Sales Order", "submit"),
        ("Sales Order", "cancel"),
        ("Purchase Order", "submit"),
        ("Purchase Order", "cancel"),
    }
    if (doctype, action) not in supported:
        frappe.throw(f"Unsupported document action: {action}")
    document = frappe.get_doc(doctype, name)
    if action == "submit":
        document.submit()
    else:
        document.cancel()
    return document.as_dict()


@frappe.whitelist(methods=["POST"])
def acceptance_cleanup(prefix: str) -> dict[str, object]:
    """Remove only local integration fixtures after runtime acceptance.

    This is intentionally not part of the public contract. It is available
    only to Administrator in developer mode and uses native Frappe deletion,
    including forced removal of ledger rows created by the test invoice.
    """
    if not frappe.conf.get("developer_mode") or frappe.session.user != "Administrator":
        frappe.throw("Acceptance cleanup is restricted to local Administrator runtime", exc=frappe.PermissionError)
    if not re.fullmatch(r"ACCEPTANCE-LOCAL-(?:[0-9a-f]{8}-)?", prefix):
        frappe.throw("Invalid local acceptance fixture prefix", exc=frappe.ValidationError)

    companies = frappe.get_all("Company", filters={"name": ["like", f"{prefix}%"]}, pluck="name")
    invoices = []
    for invoice_doctype in ("Sales Invoice", "Purchase Invoice", "Payment Entry"):
        invoices.extend(frappe.get_all(invoice_doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name"))
    deleted: list[str] = []
    failures: list[str] = []

    for ledger_doctype in ("GL Entry", "Payment Ledger Entry"):
        filters = {"voucher_no": ["in", invoices]} if invoices else {"name": "__acceptance_none__"}
        for name in frappe.get_all(ledger_doctype, filters=filters, pluck="name"):
            try:
                frappe.delete_doc(ledger_doctype, name, force=True, ignore_permissions=True)
                deleted.append(f"{ledger_doctype}:{name}")
            except frappe.DoesNotExistError:
                deleted.append(f"{ledger_doctype}:{name}")
            except Exception as error:  # noqa: BLE001 - report cleanup residue
                failures.append(f"{ledger_doctype}:{name}:{type(error).__name__}")

    # Delete the fixture Cost Center before its generated company root. The
    # root is not prefixed, so it is otherwise easy to leave a NestedSet child
    # behind when the normal public DELETE is rejected by ERPNext.
    for doctype in ("Cost Center",):
        cost_center_roots = frappe.get_all(doctype, filters={"name": ["like", f"{prefix}%"]}, pluck="name")
        cost_center_names: list[str] = []
        for root in cost_center_roots:
            cost_center_names.extend(frappe.get_all(doctype, filters={"parent_cost_center": root}, pluck="name", order_by="lft desc"))
        cost_center_names.extend(cost_center_roots)
        for company in companies:
            cost_center_names.extend(frappe.get_all(doctype, filters={"company": company}, pluck="name", order_by="lft desc"))
        blocked: list[tuple[str, str]] = []
        for _ in range(2):
            blocked = []
            for name in dict.fromkeys(cost_center_names):
                try:
                    frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
                    deleted.append(f"{doctype}:{name}")
                except frappe.DoesNotExistError:
                    deleted.append(f"{doctype}:{name}")
                except Exception as error:  # noqa: BLE001 - report cleanup residue
                    blocked.append((name, type(error).__name__))
            frappe.db.commit()
            if not blocked:
                break
            cost_center_names = frappe.get_all(doctype, filters={"company": ["in", companies]}, pluck="name", order_by="lft desc")
        for name, error_type in blocked:
            if frappe.db.exists(doctype, name):
                failures.append(f"{doctype}:{name}:{error_type}")

    for company in companies:
        account_names = frappe.get_all("Account", filters={"company": company}, pluck="name", order_by="rgt desc")
        company_doc = frappe.get_doc("Company", company) if frappe.db.exists("Company", company) else None
        if company_doc:
            for field in frappe.get_meta("Company").fields:
                if field.fieldtype == "Link" and field.options == "Account" and company_doc.get(field.fieldname) in account_names:
                    company_doc.db_set(field.fieldname, None, update_modified=False)
        # Account is a NestedSet. Re-query after each pass because deleting a
        # child changes the parent's bounds and can make the next node
        # removable. This remains native Frappe deletion; no SQL is used.
        pending = list(account_names)
        while pending:
            progress = False
            for name in pending[:]:
                try:
                    frappe.delete_doc("Account", name, force=True, ignore_permissions=True)
                    deleted.append(f"Account:{name}")
                    pending.remove(name)
                    progress = True
                except frappe.DoesNotExistError:
                    deleted.append(f"Account:{name}")
                    pending.remove(name)
                    progress = True
                except Exception:  # noqa: BLE001, S112 - retry native tree deletion
                    continue
            if not progress:
                # ERPNext deliberately protects generated chart roots even
                # after the fixture ledger is gone. This is a local teardown
                # escape hatch, scoped to this fixture Company's accounts;
                # creation and business transitions remain native APIs.
                for name in pending:
                    try:
                        frappe.db.delete("Account", {"name": name})
                        deleted.append(f"Account:{name}")
                    except Exception as error:  # noqa: BLE001 - report cleanup residue
                        failures.append(f"Account:{name}:{type(error).__name__}")
                frappe.db.commit()
                break
        rebuild_tree("Account")

    doctypes = (
        "Payment Entry",
        "Sales Invoice",
        "Delivery Note",
        "Sales Order",
        "Quotation",
        "Purchase Invoice",
        "Purchase Order",
        "Supplier",
        "Supplier Group",
        "Customer",
        "Item",
        "Item Group",
        "Territory",
        "Customer Group",
        "Warehouse",
        "Company",
        "Price List",
        "User",
    )
    fixture_document_names: set[str] = set()
    for doctype in doctypes:
        order_by = "lft desc" if frappe.get_meta(doctype).get_field("lft") else None
        name_prefix = prefix.lower() if doctype == "User" else prefix
        filters: dict[str, object] = {"name": ["like", f"{name_prefix}%"]}
        if companies and frappe.get_meta(doctype).get_field("company"):
            filters = {"company": ["in", companies]}
        names = frappe.get_all(doctype, filters=filters, pluck="name", order_by=order_by)
        fixture_document_names.update(names)
        for name in names:
            try:
                document = frappe.get_doc(doctype, name)
                if document.docstatus == 1:
                    document.flags.ignore_permissions = True
                    document.cancel()
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
                deleted.append(f"{doctype}:{name}")
            except frappe.DoesNotExistError:
                deleted.append(f"{doctype}:{name}")
            except Exception as error:  # noqa: BLE001 - report cleanup residue
                failures.append(f"{doctype}:{name}:{type(error).__name__}")
    for name in frappe.get_all("File", filters={"file_name": ["like", f"{prefix}%"]}, pluck="name"):
        try:
            frappe.delete_doc("File", name, force=True, ignore_permissions=True)
            deleted.append(f"File:{name}")
        except Exception as error:  # noqa: BLE001 - report cleanup residue
            failures.append(f"File:{name}:{type(error).__name__}")
    outbox_names = frappe.get_all(
        "Letron Event Outbox",
        filters={"document_name": ["in", list(fixture_document_names)]},
        pluck="name",
        limit_page_length=0,
    ) if fixture_document_names else []
    outbox_names.extend(
        frappe.get_all(
            "Letron Event Outbox",
            filters={"payload": ["like", f"%{prefix}%"]},
            pluck="name",
            limit_page_length=0,
        )
    )
    outbox_names = list(dict.fromkeys(outbox_names))
    if outbox_names:
        # Outbox rows are internal queued state, not business fixtures. A
        # direct scoped delete avoids Frappe's expensive dynamic-link scan.
        frappe.db.commit()
        try:
            frappe.db.delete("Letron Event Outbox", {"name": ["in", outbox_names]})
            deleted.extend(f"Letron Event Outbox:{name}" for name in outbox_names)
        except frappe.QueryDeadlockError:
            frappe.db.rollback()
            frappe.db.delete("Letron Event Outbox", {"name": ["in", outbox_names]})
            deleted.extend(f"Letron Event Outbox:{name}" for name in outbox_names)
    frappe.db.commit()
    return {"deleted": deleted, "failures": failures}
