"""Policy-driven, idempotent bootstrap for the single-Company tenant."""

from __future__ import annotations

import os
from typing import Any

import frappe

from letron_api import policy, system_config


def _restore_policy(content: str) -> None:
    source = system_config.policy_path()
    temporary = source.with_name(f".{source.name}.{os.getpid()}.rollback")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, source)
    finally:
        temporary.unlink(missing_ok=True)


def _assert_native_defaults(company: str) -> dict[str, int]:
    counts = {
        "accounts": frappe.db.count("Account", {"company": company}),
        "cost_centers": frappe.db.count("Cost Center", {"company": company}),
        "warehouses": frappe.db.count("Warehouse", {"company": company}),
        "sales_tax_templates": frappe.db.count("Sales Taxes and Charges Template", {"company": company}),
        "purchase_tax_templates": frappe.db.count("Purchase Taxes and Charges Template", {"company": company}),
        "item_tax_templates": frappe.db.count("Item Tax Template", {"company": company}),
    }
    missing = [name for name, count in counts.items() if count == 0]
    if missing:
        frappe.throw(f"Native Company bootstrap did not create: {', '.join(missing)}")
    return counts


def _ensure_company_prerequisites() -> None:
    """Seed only the native prerequisite required by ERPNext's Company hook.

    A fresh ERPNext site does not always contain the standard ``Transit``
    Warehouse Type, while ``Company.on_update`` uses it when creating default
    warehouses.  This is a controller prerequisite, not a policy-owned
    business record, and is idempotent on existing tenant sites.
    """

    if not frappe.db.exists("Warehouse Type", "Transit"):
        frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(
            ignore_permissions=True
        )


def status() -> dict[str, object]:
    desired = policy.load_policy()
    configured = desired.get("bootstrap", {}).get("company", {})
    company_name = configured.get("name")
    companies = frappe.get_all(
        "Company", fields=["name", "abbr", "country", "default_currency"], limit_page_length=0
    )
    templates: dict[str, dict[str, Any]] = {}
    for key, doctype, rate_field in (
        ("sales", "Sales Taxes and Charges Template", "rate"),
        ("purchase", "Purchase Taxes and Charges Template", "rate"),
        ("item", "Item Tax Template", "tax_rate"),
    ):
        name = frappe.db.get_value(doctype, {"company": company_name, "title": "Vietnam Tax"}, "name")
        rows = frappe.get_doc(doctype, name).get("taxes") or [] if name else []
        templates[key] = {
            "name": name,
            "rates": [float(row.get(rate_field) or 0) for row in rows],
        }
    company_matches = bool(
        len(companies) == 1
        and companies[0].name == company_name
        and companies[0].abbr == configured.get("abbreviation")
        and companies[0].country == configured.get("country")
        and companies[0].default_currency == configured.get("currency")
    )
    templates_match = all(item["name"] and item["rates"] == [10.0] for item in templates.values())
    policy_status = policy.status()
    return {
        "ok": bool(company_matches and templates_match and policy_status["ok"]),
        "company": company_name,
        "company_count": len(companies),
        "company_matches": company_matches,
        "templates": templates,
        "policy": policy_status,
    }


def run() -> dict[str, object]:
    system_config.assert_config_directory_writable()
    system_config.validate_bundle()
    source = system_config.policy_path()
    original_policy = source.read_text(encoding="utf-8")
    desired = policy.load_policy(source)
    company_config = desired["bootstrap"]["company"]
    company_name = company_config["name"]
    existing = frappe.get_all("Company", fields=["name"], limit_page_length=0)
    if len(existing) > 1:
        frappe.throw("Single-tenant instance contains more than one Company")
    if existing:
        if existing[0]["name"] != company_name:
            frappe.throw(
                f"policy.yaml declares {company_name}, but runtime Company is {existing[0]['name']}"
            )
        return {"ok": True, "created": False, "company": company_name, **_assert_native_defaults(company_name)}

    previous_flag = getattr(frappe.flags, "in_letron_bootstrap", False)
    try:
        frappe.flags.in_letron_bootstrap = True
        _ensure_company_prerequisites()
        company = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": company_name,
                "abbr": company_config["abbreviation"],
                "country": company_config["country"],
                "default_currency": company_config["currency"],
                "domain": company_config["domain"],
                "create_chart_of_accounts_based_on": "Standard Template",
                "chart_of_accounts": company_config["chart_of_accounts"],
            }
        )
        company.insert(ignore_permissions=True)
        counts = _assert_native_defaults(company_name)
        materialized = policy.materialize_native_defaults()
        frappe.db.commit()
        return {"ok": True, "created": True, "company": company_name, "policy_documents": materialized["documents"], **counts}
    except Exception:
        frappe.db.rollback()
        _restore_policy(original_policy)
        policy.reset_policy_cache()
        raise
    finally:
        frappe.flags.in_letron_bootstrap = previous_flag
