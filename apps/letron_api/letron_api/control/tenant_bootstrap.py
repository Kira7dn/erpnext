"""Policy-driven, idempotent bootstrap for a multi-Company Holding site."""

from __future__ import annotations

import os
from typing import Any

import frappe
import frappe.defaults

from letron_api.control import policy, system_config

HEADLESS_SETUP_APPS = frozenset({"frappe", "erpnext", "letron_api"})
BOOTSTRAP_STATUS_CACHE_KEY = "letron:tenant-bootstrap:status"
BOOTSTRAP_STATUS_CACHE_TTL = 60


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


def _bootstrap_companies(desired: dict[str, Any]) -> list[dict[str, str]]:
    bootstrap = desired["bootstrap"]
    return list(bootstrap.get("companies", [bootstrap["company"]]))


def _fiscal_year_definition_status(configured: dict[str, Any]) -> dict[str, object]:
    """Compare one policy Fiscal Year with its native ERPNext document."""
    name = str(configured.get("name") or "")
    native = frappe.db.get_value(
        "Fiscal Year",
        name,
        ["year", "year_start_date", "year_end_date", "disabled", "is_short_year"],
        as_dict=True,
    )
    companies = sorted(
        str(company)
        for company in frappe.get_all(
            "Fiscal Year Company",
            filters={"parent": name},
            pluck="company",
        )
        if company
    )
    expected_companies = sorted(str(company) for company in configured.get("companies", []))
    native_values = native or {}
    matches = bool(
        native
        and str(native_values.get("year") or "") == name
        and str(native_values.get("year_start_date") or "") == str(configured.get("start_date") or "")
        and str(native_values.get("year_end_date") or "") == str(configured.get("end_date") or "")
        and int(native_values.get("disabled") or 0) == 0
        and int(native_values.get("is_short_year") or 0) == 0
        and companies == expected_companies
    )
    return {
        "ok": matches,
        "configured": True,
        "name": name,
        "start_date": str(configured.get("start_date") or ""),
        "end_date": str(configured.get("end_date") or ""),
        "companies": companies,
        "expected_companies": expected_companies,
        "native_exists": bool(native),
    }


def _fiscal_year_status(desired: dict[str, Any]) -> dict[str, object]:
    """Compare current and comparative policy Fiscal Years with native records."""
    shared = desired.get("shared", {})
    configured = shared.get("fiscal_year", {})
    if not configured:
        return {"ok": True, "configured": False}

    current = _fiscal_year_definition_status(configured)
    comparative = [
        _fiscal_year_definition_status(item)
        for item in shared.get("comparative_fiscal_years", [])
    ]
    # Keep the existing current-year response contract stable while including
    # comparative years in the readiness decision.
    current["ok"] = bool(current["ok"] and all(item["ok"] for item in comparative))
    return current


def _company_identity_matches(doc: Any, config: dict[str, str]) -> bool:
    return bool(
        doc.name == config["name"]
        and doc.abbr == config["abbreviation"]
        and doc.country == config["country"]
        and doc.default_currency == config["currency"]
    )


def _ensure_group_company(group_config: dict[str, str], primary: dict[str, str]) -> str:
    name = group_config["name"]
    existing = frappe.db.exists("Company", name)
    if existing:
        group = frappe.get_doc("Company", name)
        if not group.is_group or group.abbr != group_config["abbreviation"]:
            frappe.throw(f"Existing Company {name} is not the configured Holding group")
        return name

    group = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": name,
            "abbr": group_config["abbreviation"],
            "country": primary["country"],
            "default_currency": primary["currency"],
            "domain": primary["domain"],
            "is_group": 1,
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": primary["chart_of_accounts"],
        }
    )
    group.insert(ignore_permissions=True)
    return name


def _ensure_transaction_company(config: dict[str, str], parent_company: str) -> None:
    existing = frappe.db.exists("Company", config["name"])
    if existing:
        company = frappe.get_doc("Company", config["name"])
        if not _company_identity_matches(company, config):
            frappe.throw(f"Configured Company identity does not match runtime: {config['name']}")
        if company.is_group:
            frappe.throw(f"Configured transaction Company cannot be a group: {config['name']}")
        if company.parent_company != parent_company:
            company.parent_company = parent_company
            company.save(ignore_permissions=True)
        return

    company = frappe.get_doc(
        {
            "doctype": "Company",
            "company_name": config["name"],
            "abbr": config["abbreviation"],
            "country": config["country"],
            "default_currency": config["currency"],
            "domain": config["domain"],
            "parent_company": parent_company,
            "create_chart_of_accounts_based_on": "Standard Template",
            "chart_of_accounts": config["chart_of_accounts"],
        }
    )
    company.insert(ignore_permissions=True)


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


def _complete_headless_setup() -> None:
    """Mark the UI setup state complete after the headless bootstrap.

    The headless deployment intentionally performs the setup work without the
    browser wizard.  Frappe still uses these native completion flags to decide
    whether ``/desk`` should send the user to ``/setup-wizard``.  Leaving them
    unset makes a successfully bootstrapped tenant loop between those routes.
    """

    frappe.db.set_single_value("System Settings", "setup_complete", 1)
    # The browser wizard leaves this user default at ``setup-wizard``.  A
    # headless tenant has no wizard step to finish, so Desk must be the native
    # landing route after login.
    frappe.defaults.set_global_default("desktop:home_page", "desk")
    frappe.defaults.set_user_default("desktop:home_page", "desk", "Administrator")
    installed_apps = set(frappe.get_installed_apps(_ensure_on_bench=True))
    unsupported_apps = installed_apps - HEADLESS_SETUP_APPS
    if unsupported_apps:
        frappe.throw(
            "Installed apps require explicit headless setup support: "
            + ", ".join(sorted(unsupported_apps))
        )
    for app_name in installed_apps:
        if frappe.db.exists("Installed Application", {"app_name": app_name}):
            frappe.db.set_value(
                "Installed Application",
                {"app_name": app_name},
                "is_setup_complete",
                1,
            )
    frappe.clear_cache()


def invalidate_status_cache() -> None:
    frappe.cache().delete_value(BOOTSTRAP_STATUS_CACHE_KEY)


def status(*, refresh: bool = False) -> dict[str, object]:
    desired = policy.load_policy()
    policy_hash = policy.policy_sha256(desired)
    if not refresh:
        cached = frappe.cache().get_value(BOOTSTRAP_STATUS_CACHE_KEY)
        if isinstance(cached, dict) and cached.get("policy_hash") == policy_hash:
            cached_status = cached.get("status")
            if isinstance(cached_status, dict):
                return cached_status
    bootstrap = desired.get("bootstrap", {})
    configured = bootstrap.get("company", {})
    configured_companies = _bootstrap_companies(desired) if bootstrap else []
    configured_names = {item["name"] for item in configured_companies}
    group = bootstrap.get("group")
    companies = frappe.get_all(
        "Company", fields=["name", "abbr", "country", "default_currency", "is_group", "parent_company"], limit_page_length=0
    )
    runtime_companies = {item.name: item for item in companies}
    templates_by_company: dict[str, dict[str, Any]] = {}
    for key, doctype, rate_field in (
        ("sales", "Sales Taxes and Charges Template", "rate"),
        ("purchase", "Purchase Taxes and Charges Template", "rate"),
        ("item", "Item Tax Template", "tax_rate"),
    ):
        for company_name in configured_names:
            name = frappe.db.get_value(doctype, {"company": company_name, "title": "Vietnam Tax"}, "name")
            rows = frappe.get_doc(doctype, name).get("taxes") or [] if name else []
            templates_by_company.setdefault(company_name, {})[key] = {
                "name": name,
                "rates": [float(row.get(rate_field) or 0) for row in rows],
            }
    group_matches = bool(
        isinstance(group, dict)
        and group.get("name") in runtime_companies
        and runtime_companies[group["name"]].is_group
        and runtime_companies[group["name"]].abbr == group.get("abbreviation")
    )
    company_matches = bool(
        configured_names
        and configured_names.issubset(runtime_companies)
        and all(
            _company_identity_matches(runtime_companies[name], item)
            and not runtime_companies[name].is_group
            and runtime_companies[name].parent_company == (group or {}).get("name")
            for item in configured_companies
            for name in [item["name"]]
        )
    )
    templates_match = all(
        item["name"] and item["rates"] == [10.0]
        for company_templates in templates_by_company.values()
        for item in company_templates.values()
    )
    fiscal_year = _fiscal_year_status(desired)
    policy_status = policy.status()
    setup_complete = bool(frappe.is_setup_complete())
    home_page = frappe.defaults.get_global_default("desktop:home_page")
    response = {
        "ok": bool(group_matches and company_matches and templates_match and fiscal_year["ok"] and policy_status["ok"] and setup_complete and home_page == "desk"),
        "company": configured.get("name"),
        "group": group,
        "companies": sorted(configured_names),
        "company_count": len(companies),
        "transaction_company_count": len([item for item in companies if not item.is_group]),
        "company_matches": company_matches,
        "group_matches": group_matches,
        "fiscal_year": fiscal_year,
        "templates": templates_by_company.get(configured.get("name"), {}),
        "templates_by_company": templates_by_company,
        "setup_complete": setup_complete,
        "home_page": home_page,
        "policy": policy_status,
    }
    frappe.cache().set_value(
        BOOTSTRAP_STATUS_CACHE_KEY,
        {"policy_hash": policy_hash, "status": response},
        expires_in_sec=BOOTSTRAP_STATUS_CACHE_TTL,
    )
    return response


def run() -> dict[str, object]:
    system_config.assert_config_directory_writable()
    system_config.validate_bundle()
    source = system_config.policy_path()
    original_policy = source.read_text(encoding="utf-8")
    desired = policy.load_policy(source)
    bootstrap = desired["bootstrap"]
    company_configs = _bootstrap_companies(desired)
    company_config = bootstrap["company"]
    company_name = company_config["name"]
    group_config = bootstrap.get("group", {"name": company_name, "abbreviation": company_config["abbreviation"]})
    configured_names = {item["name"] for item in company_configs}
    existing = frappe.get_all("Company", fields=["name"], limit_page_length=0)
    unexpected = {item["name"] for item in existing} - configured_names - {group_config["name"]}
    if unexpected:
        frappe.throw("Runtime contains Companies outside policy: " + ", ".join(sorted(unexpected)))

    previous_flag = getattr(frappe.flags, "in_letron_bootstrap", False)
    try:
        frappe.flags.in_letron_bootstrap = True
        _ensure_company_prerequisites()
        group_name = _ensure_group_company(group_config, company_config)
        for item in company_configs:
            _ensure_transaction_company(item, group_name)
        counts = {item["name"]: _assert_native_defaults(item["name"]) for item in company_configs}
        materialized = policy.materialize_native_defaults()
        _complete_headless_setup()
        frappe.db.commit()
        return {
            "ok": True,
            "created": not bool(existing),
            "company": company_name,
            "group": group_name,
            "companies": [item["name"] for item in company_configs],
            "policy_documents": materialized["documents"],
            "company_counts": counts,
        }
    except Exception:
        frappe.db.rollback()
        _restore_policy(original_policy)
        policy.reset_policy_cache()
        raise
    finally:
        frappe.flags.in_letron_bootstrap = previous_flag
        invalidate_status_cache()
