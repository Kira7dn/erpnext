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

    from letron_api.policy import cached_status as policy_status
    from letron_api.system_config import bundle_status
    from letron_api.system_config import cached_status as config_status
    from letron_api.tenant_bootstrap import status as bootstrap_status

    bootstrap = bootstrap_status()
    policy = policy_status()
    config = config_status()
    bundle = bundle_status()
    return {
        "ok": bool(bootstrap["ok"] and policy["ok"] and config["ok"] and bundle["ok"]),
        "app": "letron_api",
        "bootstrap": bootstrap,
        "config": config,
        "policy": policy,
        "configuration_bundle": bundle,
        **_runtime_info(),
    }


@frappe.whitelist(methods=["GET"])
def runtime_info() -> dict[str, object]:
    """Return runtime metadata used by integration verification tooling."""

    return _runtime_info()


@frappe.whitelist(methods=["GET"])
def runtime_snapshot() -> dict[str, object]:
    """Return runtime metadata used by integration verification, not business logic."""

    from letron_api.policy import status as policy_status
    from letron_api.system_config import bundle_status
    from letron_api.system_config import status as config_status
    from letron_api.tenant_bootstrap import status as bootstrap_status

    snapshot: dict[str, object] = {
        **_runtime_info(),
        "doctype_metadata": {},
        "bootstrap": bootstrap_status(),
        "config": config_status(),
        "policy": policy_status(),
        "configuration_bundle": bundle_status(),
    }
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
        ("Material Request", "submit"),
        ("Material Request", "cancel"),
        ("Purchase Receipt", "submit"),
        ("Purchase Receipt", "cancel"),
        ("Stock Entry", "submit"),
        ("Stock Entry", "cancel"),
        ("Journal Entry", "submit"),
        ("Journal Entry", "cancel"),
        ("Payment Request", "submit"),
        ("Payment Request", "cancel"),
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
    # A failed run may delete its Company before invoking this fallback while
    # ledger rows still retain that company name. Recover the scope from those
    # ledgers so teardown remains fail-closed.
    for ledger_doctype in ("GL Entry", "Payment Ledger Entry", "Stock Ledger Entry"):
        companies.extend(
            frappe.get_all(
                ledger_doctype,
                filters={"company": ["like", f"{prefix}%"]},
                pluck="company",
            )
        )
    companies = list(dict.fromkeys(companies))
    deleted: list[str] = []
    failures: list[str] = []
    fiscal_year_company_names = frappe.get_all(
        "Fiscal Year Company",
        filters={"company": ["like", f"{prefix}%"]},
        pluck="name",
    )
    if fiscal_year_company_names:
        frappe.db.delete("Fiscal Year Company", {"name": ["in", fiscal_year_company_names]})
        deleted.extend(f"Fiscal Year Company:{name}" for name in fiscal_year_company_names)
    fixture_document_names: set[str] = set()
    transaction_doctypes = (
        "Payment Request",
        "Journal Entry",
        "Sales Invoice",
        "Purchase Invoice",
        "Payment Entry",
        "Material Request",
        "Purchase Receipt",
        "Stock Entry",
    )
    vouchers: list[str] = []
    transaction_names: dict[str, list[str]] = {}
    for transaction_doctype in transaction_doctypes:
        meta = frappe.get_meta(transaction_doctype)
        filters: dict[str, object] = {"name": ["like", f"{prefix}%"]}
        if companies and meta.get_field("company"):
            filters = {"company": ["in", companies]}
        names = frappe.get_all(transaction_doctype, filters=filters, pluck="name")
        transaction_names[transaction_doctype] = names
        fixture_document_names.update(names)
        vouchers.extend(names)
        # Cancel through the native controller before removing generated
        # ledger rows. This keeps teardown valid even when a test aborts after
        # submit but before its normal cancel assertion.
        for name in names:
            document = frappe.get_doc(transaction_doctype, name)
            if document.docstatus == 1:
                try:
                    document.flags.ignore_permissions = True
                    document.cancel()
                    deleted.append(f"{transaction_doctype}:{name}:cancelled")
                except Exception as error:  # noqa: BLE001 - report cleanup residue
                    failures.append(f"{transaction_doctype}:{name}:cancel:{type(error).__name__}")
    frappe.db.commit()
    for ledger_doctype in ("GL Entry", "Payment Ledger Entry", "Stock Ledger Entry"):
        ledger_names: list[str] = []
        if vouchers:
            ledger_names.extend(frappe.get_all(ledger_doctype, filters={"voucher_no": ["in", vouchers]}, pluck="name"))
        if companies:
            ledger_names.extend(frappe.get_all(ledger_doctype, filters={"company": ["in", companies]}, pluck="name"))
        for name in dict.fromkeys(ledger_names):
            try:
                frappe.delete_doc(ledger_doctype, name, force=True, ignore_permissions=True)
                deleted.append(f"{ledger_doctype}:{name}")
            except frappe.DoesNotExistError:
                deleted.append(f"{ledger_doctype}:{name}")
            except Exception as error:  # noqa: BLE001 - report cleanup residue
                failures.append(f"{ledger_doctype}:{name}:{type(error).__name__}")

    # Journal Entry children link directly to Account, and Payment Request
    # links to its submitted invoice. Remove both after native cancellation
    # and ledger cleanup, before tearing down their referenced masters.
    for doctype in ("Payment Request", "Journal Entry"):
        for name in transaction_names.get(doctype, []):
            try:
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
                deleted.append(f"{doctype}:{name}")
            except frappe.DoesNotExistError:
                deleted.append(f"{doctype}:{name}")
            except Exception as error:  # noqa: BLE001 - report cleanup residue
                failures.append(f"{doctype}:{name}:{type(error).__name__}")
    frappe.db.commit()

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
        fixture_document_names.update(cost_center_names)
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

    # These setup documents retain Links to the fixture chart. Delete them
    # before Account NestedSet teardown so no broken child mapping remains.
    for doctype in ("Bank Account", "Mode of Payment"):
        meta = frappe.get_meta(doctype)
        filters: dict[str, object] = {"name": ["like", f"{prefix}%"]}
        if companies and meta.get_field("company"):
            filters = {"company": ["in", companies]}
        names = frappe.get_all(doctype, filters=filters, pluck="name")
        fixture_document_names.update(names)
        for name in names:
            try:
                frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
                deleted.append(f"{doctype}:{name}")
            except frappe.DoesNotExistError:
                deleted.append(f"{doctype}:{name}")
            except Exception as error:  # noqa: BLE001 - report cleanup residue
                failures.append(f"{doctype}:{name}:{type(error).__name__}")
    frappe.db.commit()

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
        "Payment Request",
        "Journal Entry",
        "Payment Entry",
        "Sales Invoice",
        "Delivery Note",
        "Sales Order",
        "Quotation",
        "Purchase Invoice",
        "Purchase Receipt",
        "Stock Entry",
        "Stock Entry Type",
        "Material Request",
        "Purchase Order",
        "Supplier",
        "Supplier Group",
        "Customer",
        "Item",
        "Item Group",
        "Territory",
        "Customer Group",
        "Warehouse",
        "Item Price",
        "Address",
        "Contact",
        "Address Template",
        "Country",
        "Bank Account",
        "Mode of Payment",
        "Bank",
        "Company",
        "Price List",
        "User",
    )
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
                if doctype == "Stock Entry Type":
                    # Custom type names are run-prefixed, but Link existence
                    # scans can still see transaction children during the
                    # same teardown. Business documents were deleted above;
                    # remove this internal prerequisite directly and scoped.
                    frappe.db.delete(doctype, {"name": name})
                    deleted.append(f"{doctype}:{name}")
                    continue
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
    # Address Template prevents deleting the active default through its
    # controller. Remove only a template whose body carries this run's prefix;
    # a pre-existing site template is reused and never matches this scope.
    acceptance_templates = frappe.get_all(
        "Address Template",
        filters={"template": ["like", f"%{prefix}%"]},
        pluck="name",
    )
    if acceptance_templates:
        frappe.db.delete("Address Template", {"name": ["in", acceptance_templates]})
        deleted.extend(f"Address Template:{name}" for name in acceptance_templates)
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
