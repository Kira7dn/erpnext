"""Native Holding finance master-data bootstrap."""

from __future__ import annotations

from typing import Any


def _finance_policy() -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str], frozenset[str]]:
    """Read the finance master catalog from the canonical policy YAML."""
    from letron_api.control.policy import load_policy

    template = load_policy().get("shared", {}).get("coa_template", {})
    accounts = template.get("accounts", [])
    coa = [dict(item) for item in accounts]
    account_types = dict(template.get("account_types", {}))
    defaults = dict(template.get("company_defaults", {}))
    legacy = frozenset(template.get("legacy_account_numbers", []))
    if not coa or len({item.get("code") for item in coa}) != len(coa):
        raise RuntimeError("shared.coa_template.accounts must contain unique accounts")
    return coa, account_types, defaults, legacy


def _configure_fiscal_year_definition(template: dict[str, Any]) -> None:
    frappe = _frappe()
    year_name = template.get("name")
    companies = template.get("companies", [])
    if not year_name or not companies:
        return
    if frappe.db.exists("Fiscal Year", year_name):
        doc = frappe.get_doc("Fiscal Year", year_name)
    else:
        doc = frappe.get_doc({
            "doctype": "Fiscal Year",
            "year": year_name,
            "year_start_date": template.get("start_date"),
            "year_end_date": template.get("end_date"),
            "disabled": 0,
            "is_short_year": 0,
        })
    changed = False
    for fieldname, expected in {
        "year": year_name,
        "year_start_date": template.get("start_date"),
        "year_end_date": template.get("end_date"),
        "disabled": 0,
        "is_short_year": 0,
    }.items():
        current = getattr(doc, fieldname, None)
        if fieldname in {"year_start_date", "year_end_date"}:
            current = str(current or "")
            expected = str(expected or "")
        elif fieldname in {"disabled", "is_short_year"}:
            current = int(current or 0)
            expected = int(expected or 0)
        if current != expected:
            setattr(doc, fieldname, expected)
            changed = True
    existing = {row.company for row in doc.companies}
    for company in companies:
        if company not in existing:
            doc.append("companies", {"company": company})
            existing.add(company)
            changed = True
    if doc.is_new():
        doc.insert(ignore_permissions=True)
    elif changed:
        doc.save(ignore_permissions=True)


def _configure_fiscal_year() -> None:
    """Materialize every policy Fiscal Year through the native DocType.

    The current year and comparative years are separate native Fiscal Year
    records.  Keeping this loop here makes a direct holding-finance apply safe
    as well; it must not rely on the later generic policy pass to create the
    comparative record by accident.
    """
    policy = _frappe().get_attr("letron_api.control.policy.load_policy")()
    shared = policy.get("shared", {})
    definitions = []
    current = shared.get("fiscal_year")
    if current:
        definitions.append(current)
    definitions.extend(shared.get("comparative_fiscal_years", []))
    for definition in definitions:
        _configure_fiscal_year_definition(dict(definition))


def _frappe() -> Any:
    import frappe

    return frappe


def _root_account(company: str, root_type: str) -> str:
    frappe = _frappe()
    candidates = frappe.get_all(
        "Account",
        filters={"company": company, "root_type": root_type, "is_group": 1},
        fields=["name", "parent_account", "lft"],
        order_by="lft asc",
        limit_page_length=0,
    )
    root = next((item.name for item in candidates if not item.parent_account), None)
    if not root and candidates:
        root = candidates[0].name
    if not root:
        raise RuntimeError(f"Missing native {root_type} root for {company}")
    return root


def _parent_code(item: dict[str, Any], codes: set[str]) -> str | None:
    explicit = item.get("parent_code")
    if explicit:
        return str(explicit)
    code = str(item["code"])
    return max(
        (candidate for candidate in codes if candidate != code and code.startswith(candidate)),
        key=len,
        default=None,
    )


def _ensure_group(account_name: str) -> None:
    """Convert a ledger parent through the native Account controller."""
    frappe = _frappe()
    doc = frappe.get_doc("Account", account_name)
    if int(doc.is_group):
        return
    if frappe.db.exists("GL Entry", {"account": account_name}):
        raise RuntimeError(f"Cannot convert posted Account to group: {account_name}")
    doc.is_group = 1
    doc.account_type = None
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)


def _ensure_account_for_company(
    company: str,
    item: dict[str, Any],
    account_types: dict[str, str],
    codes: set[str],
    accounts_by_code: dict[str, Any],
) -> tuple[str, bool]:
    frappe = _frappe()
    code = str(item["code"])
    root_type = str(item["root_type"])
    existing = accounts_by_code.get(code)
    has_children = any(other != code and other.startswith(code) for other in codes)
    if existing:
        if str(existing.root_type) != root_type:
            raise RuntimeError(
                f"Account {company}/{code} has root_type {existing.root_type}, expected {root_type}"
            )
        if has_children and not int(existing.is_group):
            _ensure_group(existing.name)
            existing.is_group = 1
        account_type = account_types.get(code)
        if account_type and str(existing.account_type or "") != account_type:
            frappe.db.set_value("Account", existing.name, "account_type", account_type, update_modified=False)
            existing.account_type = account_type
        return existing.name, False

    parent_code = _parent_code(item, codes)
    parent = accounts_by_code.get(parent_code) if parent_code else None
    if parent_code and not parent:
        raise RuntimeError(f"Missing parent account {company}/{parent_code}")
    if parent:
        if not int(parent.is_group):
            _ensure_group(parent.name)
            parent.is_group = 1
        parent_name = parent.name
    else:
        parent_name = _root_account(company, root_type)

    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": str(item["name"]),
            "account_number": code,
            "company": company,
            "root_type": root_type,
            "account_type": account_types.get(code),
            "is_group": int(item.get("is_group", has_children)),
            "parent_account": parent_name,
        }
    )
    doc.insert(ignore_permissions=True)
    accounts_by_code[code] = doc
    return doc.name, True


def _materialize_company(
    company: str,
    coa: list[dict[str, Any]],
    account_types: dict[str, str],
    codes: set[str],
) -> int:
    frappe = _frappe()
    accounts_by_code = {
        str(row.account_number): row
        for row in frappe.get_all(
            "Account",
            filters={"company": company, "account_number": ["is", "set"]},
            fields=["name", "account_number", "root_type", "is_group", "account_type"],
            limit_page_length=0,
        )
        if row.account_number
    }
    created = 0
    for item in sorted(coa, key=lambda value: (len(str(value["code"])), str(value["code"]))):
        _, was_created = _ensure_account_for_company(
            company, item, account_types, codes, accounts_by_code
        )
        created += int(was_created)
    return created


def _retire_legacy_accounts(companies: list[str], legacy_codes: frozenset[str]) -> int:
    frappe = _frappe()
    retired = 0
    for account in frappe.get_all(
        "Account",
        filters={"company": ["in", companies], "account_number": ["in", list(legacy_codes)]},
        fields=["name", "disabled"],
        limit_page_length=0,
    ):
        if account.disabled or frappe.db.exists("GL Entry", {"account": account.name}):
            continue
        frappe.db.set_value("Account", account.name, "disabled", 1, update_modified=False)
        retired += 1
    return retired


def _configure_company_defaults(companies: list[str], defaults: dict[str, str]) -> None:
    frappe = _frappe()
    for company in companies:
        for fieldname, code in defaults.items():
            account_name = frappe.db.get_value(
                "Account", {"company": company, "account_number": code}, "name"
            )
            if account_name:
                frappe.db.set_value("Company", company, fieldname, account_name, update_modified=False)


def _configure_tax_accounts(companies: list[str]) -> None:
    frappe = _frappe()
    previous_flag = getattr(frappe.flags, "in_letron_policy_apply", False)
    frappe.flags.in_letron_policy_apply = True
    templates = {
        "Purchase Taxes and Charges Template": "1331",
        "Sales Taxes and Charges Template": "33311",
        "Item Tax Template": "33311",
    }
    try:
        for company in companies:
            for doctype, code in templates.items():
                template_name = frappe.db.get_value(
                    doctype, {"company": company, "title": "Vietnam Tax"}, "name"
                )
                account_name = frappe.db.get_value(
                    "Account", {"company": company, "account_number": code}, "name"
                )
                if not template_name or not account_name:
                    continue
                doc = frappe.get_doc(doctype, template_name)
                if not doc.taxes:
                    continue
                fieldname = "tax_type" if doctype == "Item Tax Template" else "account_head"
                changed = False
                for row in doc.taxes:
                    if getattr(row, fieldname) != account_name:
                        setattr(row, fieldname, account_name)
                        changed = True
                if changed:
                    doc.save(ignore_permissions=True)
    finally:
        frappe.flags.in_letron_policy_apply = previous_flag


def _expected_tax_account_code(doctype: str) -> str:
    """Return the VAS account required by each native tax template type."""
    expected = {
        "Purchase Taxes and Charges Template": "1331",
        "Sales Taxes and Charges Template": "33311",
        "Item Tax Template": "33311",
    }
    try:
        return expected[doctype]
    except KeyError as error:
        raise ValueError(f"Unsupported tax template DocType: {doctype}") from error


def _validate_tax_accounts(companies: list[str]) -> dict[str, dict[str, str]]:
    """Fail closed if a VAT template points to an account with the wrong nature."""
    frappe = _frappe()
    result: dict[str, dict[str, str]] = {}
    for company in companies:
        result[company] = {}
        for doctype in (
            "Purchase Taxes and Charges Template",
            "Sales Taxes and Charges Template",
            "Item Tax Template",
        ):
            template_name = frappe.db.get_value(
                doctype, {"company": company, "title": "Vietnam Tax"}, "name"
            )
            if not template_name:
                raise RuntimeError(f"Missing Vietnam Tax template: {doctype}/{company}")
            document = frappe.get_doc(doctype, template_name)
            rows = list(document.taxes or [])
            if not rows:
                raise RuntimeError(f"Vietnam Tax template has no tax rows: {doctype}/{company}")
            fieldname = "tax_type" if doctype == "Item Tax Template" else "account_head"
            expected_code = _expected_tax_account_code(doctype)
            for row in rows:
                account = getattr(row, fieldname, None)
                actual_code = frappe.db.get_value("Account", account, "account_number")
                if str(actual_code or "") != expected_code:
                    raise RuntimeError(
                        f"{doctype}/{company} must use Account {expected_code}; "
                        f"found {actual_code or account}"
                    )
            result[company][doctype] = expected_code
    return result


def _ensure_consolidation_finance_book() -> str | None:
    """Materialize the policy-owned adjustment book through the native DocType."""
    frappe = _frappe()
    policy = frappe.get_attr("letron_api.control.policy.load_policy")()
    settings = policy.get("shared", {}).get("consolidation", {})
    name = settings.get("finance_book")
    if not name:
        return None
    if not frappe.db.exists("Finance Book", name):
        doc = frappe.get_doc({"doctype": "Finance Book", "finance_book_name": name})
        doc.insert(ignore_permissions=True)
    return str(name)


def apply() -> dict[str, Any]:
    frappe = _frappe()
    coa, account_types, defaults, legacy_codes = _finance_policy()
    group_companies = frappe.get_all("Company", filters={"is_group": 1}, pluck="name", limit_page_length=0)
    if len(group_companies) != 1:
        raise RuntimeError(f"Expected exactly one Holding root Company, found: {group_companies}")

    root_company = group_companies[0]
    codes = {str(item["code"]) for item in coa}
    from frappe.utils.nestedset import rebuild_tree

    companies = frappe.get_all("Company", pluck="name", limit_page_length=0)
    previous_ignore_nsm = getattr(frappe.local.flags, "ignore_update_nsm", False)
    previous_ignore_root = getattr(frappe.local.flags, "ignore_root_company_validation", False)
    frappe.local.flags.ignore_update_nsm = True
    frappe.local.flags.ignore_root_company_validation = True
    try:
        created = sum(
            _materialize_company(company, coa, account_types, codes)
            for company in companies
        )
    finally:
        frappe.local.flags.ignore_update_nsm = previous_ignore_nsm
        frappe.local.flags.ignore_root_company_validation = previous_ignore_root
    rebuild_tree("Account")

    transaction_companies = frappe.get_all(
        "Company", filters={"is_group": 0}, pluck="name", limit_page_length=0
    )
    all_companies = list(companies)
    _configure_fiscal_year()
    _configure_company_defaults(all_companies, defaults)
    _configure_tax_accounts(all_companies)
    # The Company group is a reporting node, not a transaction entity and must
    # not carry VAT templates or tax-account defaults.
    tax_accounts = _validate_tax_accounts(transaction_companies)
    consolidation_finance_book = _ensure_consolidation_finance_book()
    retired_legacy_accounts = _retire_legacy_accounts(all_companies, legacy_codes)
    result = {company: 0 for company in companies}
    for company in companies:
        for code, account_type in account_types.items():
            account_name = frappe.db.get_value(
                "Account", {"company": company, "account_number": code}, "name"
            )
            if account_name:
                frappe.db.set_value(
                    "Account", account_name, "account_type", account_type, update_modified=False
                )
        result[company] = sum(
            1
            for item in coa
            if frappe.db.exists("Account", {"company": company, "account_number": item["code"]})
        )
    frappe.db.commit()
    return {
        "ok": True,
        "root_company": root_company,
        "companies": len(transaction_companies),
        "created_accounts": created,
        "retired_legacy_accounts": retired_legacy_accounts,
        "account_count_by_company": result,
        "account_template_count": len(coa),
        "tax_accounts": tax_accounts,
        "consolidation_finance_book": consolidation_finance_book,
    }
