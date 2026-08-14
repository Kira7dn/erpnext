"""Disposable native fixture registry for the Phase 8 policy contract.

The registry is importable without Frappe so unit tests can prove that every
machine-readable scope mapping resolves to a concrete builder. Runtime helpers
are deliberately kept behind functions and are only called on acceptance sites.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FIXTURE_PREFIX = "acceptance-local-phase8-"

CONTROLLER_EFFECT_ASSERTIONS = {
    "Payment Terms Template": "probe_payment_terms_effect",
    "Pricing Rule": "probe_pricing_shipping_effects",
    "Promotional Scheme": "probe_pricing_shipping_effects",
    "Shipping Rule": "probe_pricing_shipping_effects",
    "Stock Entry Type": "probe_stock_buying_effects",
    "Quality Inspection Template": "probe_stock_buying_effects",
    "Supplier Scorecard": "probe_stock_buying_effects",
    "Workflow": "probe_cross_cutting_effects",
    "Custom DocPerm": "probe_cross_cutting_effects",
    "Document Naming Rule": "probe_cross_cutting_effects",
    "Print Format": "probe_cross_cutting_effects",
    "Letter Head": "probe_cross_cutting_effects",
    "Email Template": "probe_cross_cutting_effects",
    "Notification": "probe_cross_cutting_effects",
    "Assignment Rule": "probe_cross_cutting_effects",
    "Sales Taxes and Charges Template": "probe_tax_effect_rate",
    "Purchase Taxes and Charges Template": "probe_tax_effect_rate",
    "Item Tax Template": "probe_tax_effect_rate",
    "Tax Category": "probe_tax_effect_rate",
    "Tax Rule": "probe_tax_effect_rate",
}

SINGLE_BUILDERS = {
    "Accounts Settings",
    "Buying Settings",
    "Currency Exchange Settings",
    "Delivery Settings",
    "Global Defaults",
    "Item Variant Settings",
    "Ledger Health Monitor",
    "Pegged Currencies",
    "Print Settings",
    "Selling Settings",
    "Stock Reposting Settings",
    "Stock Settings",
}

SINGLE_UPDATE_FIELDS = {
    "Accounts Settings": "check_supplier_invoice_uniqueness",
    "Buying Settings": "show_pay_button",
    "Currency Exchange Settings": "disabled",
    "Delivery Settings": "stop_delay",
    "Global Defaults": "hide_currency_symbol",
    "Item Variant Settings": "allow_rename_attribute_value",
    "Ledger Health Monitor": "monitor_for_last_x_days",
    "Pegged Currencies": None,
    "Print Settings": "with_repeat_header",
    "Selling Settings": "allow_zero_qty_in_quotation",
    "Stock Reposting Settings": "no_of_parallel_reposting",
    "Stock Settings": "show_barcode_field",
}

DOCUMENT_UPDATE_FIELDS: dict[str, str | None] = {
    "Role": "desk_access",
    "Role Profile": None,
    "Workflow State": None,
    "Workflow Action Master": None,
    "Custom DocPerm": "write",
    "Assignment Rule": "disabled",
    "Document Naming Rule": "disabled",
    "Print Format": "disabled",
    "Letter Head": "disabled",
    "Email Template": "use_html",
    "Notification": "enabled",
    "Workflow": "is_active",
    "Fiscal Year": "disabled",
    "Accounting Dimension": "disabled",
    "Accounting Dimension Filter": "disabled",
    "Accounting Period": None,
    "Bank Transaction Rule": "priority",
    "Cheque Print Template": None,
    "Cost Center Allocation": None,
    "Dunning Type": "dunning_fee",
    "Financial Report Template": None,
    "Item Tax Template": "disabled",
    "Journal Entry Template": None,
    "Loyalty Program": "auto_opt_in",
    "Monthly Distribution": None,
    "Payment Term": "credit_days",
    "Payment Terms Template": None,
    "Pricing Rule": "disable",
    "Promotional Scheme": "disable",
    "Purchase Taxes and Charges Template": "disabled",
    "Sales Taxes and Charges Template": "disabled",
    "Shipping Rule": "disabled",
    "Tax Category": "disabled",
    "Tax Rule": "priority",
    "Tax Withholding Category": "disable_cumulative_threshold",
    "Tax Withholding Group": None,
    "Terms and Conditions": "disabled",
    "Supplier Scorecard": None,
    "Inventory Dimension": "validate_negative_stock",
    "Putaway Rule": "disable",
    "Quality Inspection Template": None,
    "Shipment Parcel Template": "weight",
    "Stock Entry Type": "add_to_transit",
}


def _fixture_name(doctype: str) -> str:
    return f"{FIXTURE_PREFIX}{doctype.lower().replace(' ', '-')}"


DOCUMENT_BUILDERS: dict[str, dict[str, Any]] = {
    "Role": {"role_name": _fixture_name("Role"), "is_custom": 1, "desk_access": 1},
    "Role Profile": {
        "role_profile": _fixture_name("Role Profile"),
        "roles": [{"role": _fixture_name("Role")}],
    },
    "Workflow State": {
        "workflow_state_name": _fixture_name("Workflow State"),
        "style": "Primary",
    },
    "Workflow Action Master": {
        "workflow_action_name": _fixture_name("Workflow Action Master")
    },
    "Company": {},
    "Fiscal Year": {
        "year": "2042",
        "year_start_date": "2042-01-01",
        "year_end_date": "2042-12-31",
        "companies": [{"company": "$company"}],
    },
    "Accounting Dimension": {
        "label": "Acceptance Dimension",
        "document_type": "Supplier",
        "disabled": 0,
    },
    "Accounting Dimension Filter": {
        "accounting_dimension": "Acceptance Dimension",
        "allow_or_restrict": "Allow",
        "company": "$company",
        "accounts": [{"applicable_on_account": "$expense_account"}],
        "disabled": 0,
    },
    "Accounting Period": {
        "period_name": _fixture_name("Accounting Period"),
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "company": "$company",
        "closed_documents": [{"document_type": "Sales Invoice", "closed": 0}],
    },
    "Bank Transaction Rule": {
        "rule_name": _fixture_name("Bank Transaction Rule"),
        "transaction_type": "Any",
        "classify_as": "Bank Entry",
        "priority": 100,
        "company": "$company",
        "account": "$bank_account",
        "description_rules": [{"check": "Contains", "value": "Phase 8"}],
        "accounts": [{"account": "$bank_account"}],
    },
    "Supplier Scorecard": {
        "supplier": "$supplier",
        "period": "Per Month",
        "weighting_function": "0.0",
        "criteria": [{"criteria_name": "$scorecard_criterion", "weight": 100.0}],
        "standings": [
            {"standing_color": "Green", "min_grade": 0.0, "max_grade": 100.0}
        ],
    },
    "Inventory Dimension": {
        "reference_document": "Supplier",
        "dimension_name": "Acceptance Inventory Dimension",
    },
    "Putaway Rule": {
        "item_code": "$item",
        "warehouse": "$warehouse",
        "capacity": 100.0,
        "company": "$company",
        "priority": 100,
    },
    "Quality Inspection Template": {
        "quality_inspection_template_name": _fixture_name(
            "Quality Inspection Template"
        ),
        "item_quality_inspection_parameter": [
            {
                "specification": "$quality_parameter",
                "numeric": 1,
                "min_value": 0.0,
                "max_value": 10.0,
            }
        ],
    },
    "Shipment Parcel Template": {
        "parcel_template_name": _fixture_name("Shipment Parcel Template"),
        "length": 10.0,
        "width": 10.0,
        "height": 10.0,
        "weight": 1.0,
    },
    "Stock Entry Type": {"purpose": "Material Transfer", "add_to_transit": 0},
    "Cheque Print Template": {
        "bank_name": _fixture_name("Cheque Print Template"),
        "cheque_size": "Regular",
    },
    "Cost Center": {
        "cost_center_name": _fixture_name("Cost Center"),
        "parent_cost_center": "$parent_cost_center",
        "company": "$company",
        "is_group": 0,
        "disabled": 0,
    },
    "Cost Center Allocation": {
        "main_cost_center": "$cost_center",
        "valid_from": "2042-01-01",
        "company": "$company",
        "allocation_percentages": [
            {"cost_center": "$allocation_cost_center", "percentage": 100.0}
        ],
    },
    "Dunning Type": {
        "dunning_type": _fixture_name("Dunning Type"),
        "company": "$company",
        "dunning_fee": 0.0,
        "rate_of_interest": 0.0,
        "dunning_letter_text": [
            {
                "language": "en",
                "is_default_language": 1,
                "body_text": "Phase 8",
                "closing_text": "Done",
            }
        ],
    },
    "Financial Report Template": {
        "template_name": _fixture_name("Financial Report Template"),
        "report_type": "Balance Sheet",
        "rows": [{"display_name": "Phase 8", "data_source": "Blank Line"}],
    },
    "Item Tax Template": {
        "title": "Acceptance Tax 0",
        "company": "$company",
        "disabled": 0,
        "taxes": [{"tax_type": "$tax_account", "tax_rate": 0.0}],
    },
    "Journal Entry Template": {
        "voucher_type": "Journal Entry",
        "company": "$company",
        "naming_series": "ACC-JV-.YYYY.-",
        "template_title": _fixture_name("Journal Entry Template"),
        "accounts": [{"account": "$expense_account", "cost_center": "$cost_center"}],
    },
    "Loyalty Program": {
        "loyalty_program_name": _fixture_name("Loyalty Program"),
        "from_date": "2042-01-01",
        "to_date": "2042-12-31",
        "company": "$company",
        "collection_rules": [
            {"tier_name": "Base", "collection_factor": 1.0, "min_spent": 0.0}
        ],
    },
    "Monthly Distribution": {
        "distribution_id": _fixture_name("Monthly Distribution"),
        "percentages": [{"month": "January", "percentage_allocation": 100.0}],
    },
    "Payment Term": {
        "payment_term_name": _fixture_name("Payment Term"),
        "invoice_portion": 100.0,
        "due_date_based_on": "Day(s) after invoice date",
        "credit_days": 0,
    },
    "Payment Terms Template": {
        "template_name": _fixture_name("Payment Terms Template"),
        "terms": [
            {
                "payment_term": _fixture_name("Payment Term"),
                "invoice_portion": 100.0,
                "due_date_based_on": "Day(s) after invoice date",
                "credit_days": 0,
            }
        ],
    },
    "Pricing Rule": {
        "title": _fixture_name("Pricing Rule"),
        "apply_on": "Item Code",
        "price_or_product_discount": "Price",
        "currency": "VND",
        "selling": 1,
        "items": [{"item_code": "$item"}],
        "rate_or_discount": "Discount Percentage",
        "discount_percentage": 5.0,
        "valid_from": "2042-01-01",
        "valid_upto": "2042-12-31",
    },
    "Promotional Scheme": {
        "apply_on": "Item Code",
        "company": "$company",
        "selling": 1,
        "items": [{"item_code": "$item"}],
        "price_discount_slabs": [
            {
                "rule_description": "Phase 8",
                "min_qty": 1.0,
                "rate_or_discount": "Discount Percentage",
                "discount_percentage": 5.0,
            }
        ],
    },
    "Purchase Taxes and Charges Template": {
        "title": "Acceptance Purchase Tax 0",
        "company": "$company",
        "disabled": 0,
        "taxes": [
            {
                "category": "Total",
                "add_deduct_tax": "Add",
                "charge_type": "On Net Total",
                "account_head": "$tax_account",
                "description": "Tax 0%",
                "cost_center": "$cost_center",
                "rate": 0.0,
            }
        ],
    },
    "Sales Taxes and Charges Template": {
        "title": "Acceptance Sales Tax 0",
        "company": "$company",
        "disabled": 0,
        "taxes": [
            {
                "charge_type": "On Net Total",
                "account_head": "$tax_account",
                "description": "Tax 0%",
                "cost_center": "$cost_center",
                "rate": 0.0,
            }
        ],
    },
    "Shipping Rule": {
        "label": _fixture_name("Shipping Rule"),
        "company": "$company",
        "account": "$income_account",
        "shipping_rule_type": "Selling",
        "calculate_based_on": "Net Total",
        "conditions": [
            {"from_value": 0.0, "to_value": 1000000.0, "shipping_amount": 1000.0}
        ],
    },
    "Tax Category": {"title": _fixture_name("Tax Category"), "disabled": 0},
    "Tax Rule": {
        "tax_type": "Sales",
        "company": "$company",
        "tax_category": _fixture_name("Tax Category"),
        "sales_tax_template": "$sales_tax_template",
        "from_date": "2042-01-01",
        "to_date": "2042-12-31",
    },
    "Tax Withholding Category": {
        "category_name": _fixture_name("Tax Withholding Category"),
        "tax_deduction_basis": "Net Total",
        "rates": [
            {
                "tax_withholding_rate": 5.0,
                "from_date": "2042-01-01",
                "to_date": "2042-12-31",
            }
        ],
        "accounts": [{"company": "$company", "account": "$tax_account"}],
    },
    "Tax Withholding Group": {"group_name": _fixture_name("Tax Withholding Group")},
    "Terms and Conditions": {
        "title": _fixture_name("Terms and Conditions"),
        "terms": "<p>Điều khoản Phase 8</p>",
        "disabled": 0,
    },
    "Custom DocPerm": {
        "parent": "Quotation",
        "role": _fixture_name("Role"),
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
    },
    "Assignment Rule": {
        "document_type": "Quotation",
        "description": "Phase 8 assignment",
        "assign_condition": "True",
        "rule": "Round Robin",
        "users": [{"user": "Administrator"}],
        "disabled": 1,
        "assignment_days": [{"day": "Monday"}],
    },
    "Document Naming Rule": {
        "document_type": "Quotation",
        "prefix": "P8-QTN-",
        "prefix_digits": 5,
        "disabled": 1,
        "conditions": [],
    },
    "Print Format": {
        "standard": "No",
        "doc_type": "Quotation",
        "print_format_type": "Jinja",
        "html": "<p>{{ doc.name }}</p>",
        "disabled": 0,
    },
    "Letter Head": {
        "letter_head_name": _fixture_name("Letter Head"),
        "source": "HTML",
        "content": "<div>Letron Phase 8</div>",
        "footer": "<div>{{ doc.name }}</div>",
        "disabled": 0,
    },
    "Email Template": {
        "subject": "Phase 8 {{ name }}",
        "use_html": 1,
        "response_html": "<p>Xin chào {{ name }}</p>",
    },
    "Notification": {
        "channel": "System Notification",
        "document_type": "Quotation",
        "event": "New",
        "subject": "Phase 8 {{ doc.name }}",
        "message": "<p>{{ doc.name }}</p>",
        "enabled": 0,
        "recipients": [{"receiver_by_role": _fixture_name("Role")}],
    },
    "Workflow": {
        "workflow_name": _fixture_name("Workflow"),
        "document_type": "Quotation",
        "workflow_state_field": "workflow_state",
        "is_active": 0,
        "states": [
            {
                "state": _fixture_name("Workflow State"),
                "doc_status": "0",
                "allow_edit": _fixture_name("Role"),
            }
        ],
        "transitions": [
            {
                "state": _fixture_name("Workflow State"),
                "action": _fixture_name("Workflow Action Master"),
                "next_state": _fixture_name("Workflow State"),
                "allowed": _fixture_name("Role"),
                "allow_self_approval": 1,
            }
        ],
    },
}


def resolve_builder(builder_id: str) -> tuple[str, str]:
    """Resolve one scope builder ID or fail closed."""

    kind, separator, doctype = builder_id.partition(":")
    if not separator:
        raise KeyError(builder_id)
    if kind == "native-single" and doctype in SINGLE_BUILDERS:
        return kind, doctype
    if kind == "native-document" and doctype in DOCUMENT_BUILDERS:
        return kind, doctype
    raise KeyError(builder_id)


def resolve_controller_effect_assertion(
    assertion_id: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve every machine-readable assertion label to executable work."""

    prefix, separator, doctype = assertion_id.partition(":")
    if prefix != "native-controller" or not separator:
        raise KeyError(assertion_id)
    resolve_builder(
        f"native-single:{doctype}"
        if doctype in SINGLE_BUILDERS
        else f"native-document:{doctype}"
    )
    method = CONTROLLER_EFFECT_ASSERTIONS.get(doctype)
    if method == "probe_tax_effect_rate":
        return method, {"rate": 10}
    if method == "probe_cross_cutting_effects":
        effects = {
            "Document Naming Rule": "naming",
            "Print Format": "render",
            "Letter Head": "render",
            "Email Template": "render",
            "Notification": "notification_assignment",
            "Assignment Rule": "notification_assignment",
            "Workflow": "workflow_permission",
            "Custom DocPerm": "workflow_permission",
        }
        return method, {"effect": effects[doctype]}
    if method:
        return method, {}
    return "probe_registry_source", {"doctype": doctype}


def fixture_fields(doctype: str, prerequisites: Mapping[str, str]) -> dict[str, Any]:
    """Return a fresh fixture mapping with prerequisite tokens resolved."""

    import copy

    fields = copy.deepcopy(DOCUMENT_BUILDERS[doctype])

    def resolve(value: Any) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            return prerequisites[value[1:]]
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            return {key: resolve(item) for key, item in value.items()}
        return value

    return resolve(fields)


def _runtime_prerequisites() -> dict[str, str]:
    import frappe

    from letron_api.policy import load_policy

    company = load_policy()["bootstrap"]["company"]["name"]

    def account(**filters: Any) -> str:
        filters["company"] = company
        name = frappe.db.get_value("Account", filters, "name")
        if not name:
            raise RuntimeError(f"Missing acceptance Account prerequisite: {filters}")
        return str(name)

    cost_centers = frappe.get_all(
        "Cost Center",
        filters={
            "company": company,
            "is_group": 0,
            "name": ["not like", "Phase8 Allocation%"],
        },
        pluck="name",
        limit_page_length=1,
    )
    cost_center = cost_centers[0] if cost_centers else None
    parent_cost_center = frappe.db.get_value(
        "Cost Center", {"company": company, "is_group": 1}, "name"
    )
    warehouse = frappe.db.get_value(
        "Warehouse", {"company": company, "is_group": 0}, "name"
    )
    if not cost_center or not parent_cost_center or not warehouse:
        raise RuntimeError("Missing acceptance Cost Center/Warehouse prerequisite")
    return {
        "company": company,
        "cost_center": str(cost_center),
        "parent_cost_center": str(parent_cost_center),
        "allocation_cost_center": (
            f"Phase8 Allocation - {frappe.db.get_value('Company', company, 'abbr')}"
        ),
        "warehouse": str(warehouse),
        "tax_account": account(account_type="Tax"),
        "bank_account": account(account_type="Bank"),
        "income_account": account(root_type="Income", is_group=0),
        "expense_account": account(root_type="Expense", is_group=0),
        "sales_tax_template": "Vietnam Tax - LTVN",
        "item_group": str(
            frappe.db.get_value("Item Group", {}, "name") or "All Item Groups"
        ),
        "uom": str(frappe.db.get_value("UOM", {}, "name") or "Nos"),
        "supplier_group": str(
            frappe.db.get_value("Supplier Group", {}, "name") or "All Supplier Groups"
        ),
        "customer_group": str(
            frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
            or _fixture_name("Customer Group")
        ),
        "territory": str(
            frappe.db.get_value("Territory", {"is_group": 0}, "name")
            or _fixture_name("Territory")
        ),
        "selling_price_list": str(
            frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
            or _fixture_name("Selling Price List")
        ),
        "buying_price_list": str(
            frappe.db.get_value("Price List", {"buying": 1, "enabled": 1}, "name")
            or _fixture_name("Buying Price List")
        ),
        "item": _fixture_name("Item"),
        "tax_item": _fixture_name("Tax Item"),
        "customer": _fixture_name("Customer"),
        "supplier": _fixture_name("Supplier"),
        "quality_parameter": _fixture_name("Quality Inspection Parameter"),
        "scorecard_criterion": _fixture_name("Supplier Scorecard Criteria"),
    }


def _ensure_probe_prerequisites(
    values: Mapping[str, str], *, include_policy_dependencies: bool = True
) -> None:
    import frappe

    roots = [
        {"doctype": "UOM", "name": values["uom"], "uom_name": values["uom"]},
        {
            "doctype": "Item Group",
            "name": values["item_group"],
            "item_group_name": values["item_group"],
            "is_group": 1,
        },
        {
            "doctype": "Supplier Group",
            "name": values["supplier_group"],
            "supplier_group_name": values["supplier_group"],
            "is_group": 1,
        },
        {
            "doctype": "Customer Group",
            "name": _fixture_name("Customer Group Root"),
            "customer_group_name": _fixture_name("Customer Group Root"),
            "is_group": 1,
        },
        {
            "doctype": "Territory",
            "name": _fixture_name("Territory Root"),
            "territory_name": _fixture_name("Territory Root"),
            "is_group": 1,
        },
        {
            "doctype": "Customer Group",
            "name": values["customer_group"],
            "customer_group_name": values["customer_group"],
            "parent_customer_group": _fixture_name("Customer Group Root"),
            "is_group": 0,
        },
        {
            "doctype": "Price List",
            "name": values["selling_price_list"],
            "price_list_name": values["selling_price_list"],
            "currency": "VND",
            "selling": 1,
            "enabled": 1,
        },
        {
            "doctype": "Price List",
            "name": values["buying_price_list"],
            "price_list_name": values["buying_price_list"],
            "currency": "VND",
            "buying": 1,
            "enabled": 1,
        },
        {
            "doctype": "Territory",
            "name": values["territory"],
            "territory_name": values["territory"],
            "parent_territory": _fixture_name("Territory Root"),
            "is_group": 0,
        },
    ]
    for value in roots:
        if not frappe.db.exists(str(value["doctype"]), str(value["name"])):
            frappe.get_doc(value).insert(ignore_permissions=True)

    documents = [
        {
            "doctype": "Cost Center",
            "name": values["allocation_cost_center"],
            "cost_center_name": "Phase8 Allocation",
            "parent_cost_center": values["parent_cost_center"],
            "company": values["company"],
            "is_group": 0,
        },
        {
            "doctype": "Item",
            "name": values["item"],
            "item_code": values["item"],
            "item_name": values["item"],
            "item_group": values["item_group"],
            "stock_uom": values["uom"],
            "is_stock_item": 1,
        },
        {
            "doctype": "Supplier",
            "name": values["supplier"],
            "supplier_name": values["supplier"],
            "supplier_group": values["supplier_group"],
            "supplier_type": "Company",
        },
        {
            "doctype": "Item",
            "name": values["tax_item"],
            "item_code": values["tax_item"],
            "item_name": values["tax_item"],
            "item_group": values["item_group"],
            "stock_uom": values["uom"],
            "is_stock_item": 0,
        },
        {
            "doctype": "Customer",
            "name": values["customer"],
            "customer_name": values["customer"],
            "customer_group": values["customer_group"],
            "territory": values["territory"],
            "customer_type": "Company",
        },
        {
            "doctype": "Quality Inspection Parameter",
            "name": values["quality_parameter"],
            "parameter": values["quality_parameter"],
        },
        {
            "doctype": "Supplier Scorecard Criteria",
            "name": values["scorecard_criterion"],
            "criteria_name": values["scorecard_criterion"],
            "max_score": 100.0,
            "formula": "0",
        },
    ]
    if include_policy_dependencies:
        documents.extend(
            [
                {
                    "doctype": "Payment Term",
                    "name": _fixture_name("Payment Term"),
                    "payment_term_name": _fixture_name("Payment Term"),
                    "invoice_portion": 100.0,
                    "due_date_based_on": "Day(s) after invoice date",
                    "credit_days": 0,
                },
                {
                    "doctype": "Tax Category",
                    "name": _fixture_name("Tax Category"),
                    "title": _fixture_name("Tax Category"),
                    "disabled": 0,
                },
                {
                    "doctype": "Role",
                    "name": _fixture_name("Role"),
                    "role_name": _fixture_name("Role"),
                    "is_custom": 1,
                    "desk_access": 1,
                },
                {
                    "doctype": "Workflow State",
                    "name": _fixture_name("Workflow State"),
                    "workflow_state_name": _fixture_name("Workflow State"),
                    "style": "Primary",
                },
                {
                    "doctype": "Workflow Action Master",
                    "name": _fixture_name("Workflow Action Master"),
                    "workflow_action_name": _fixture_name("Workflow Action Master"),
                },
            ]
        )
    for value in documents:
        if not frappe.db.exists(str(value["doctype"]), str(value["name"])):
            frappe.get_doc(value).insert(ignore_permissions=True)


def _document_name(doctype: str, fields: Mapping[str, Any]) -> str:
    explicit = fields.get("name")
    if explicit:
        return str(explicit)
    names = {
        "Role": "role_name",
        "Role Profile": "role_profile",
        "Workflow State": "workflow_state_name",
        "Workflow Action Master": "workflow_action_name",
        "Fiscal Year": "year",
        "Accounting Dimension": "label",
        "Accounting Period": "period_name",
        "Bank Transaction Rule": "rule_name",
        "Supplier Scorecard": "supplier",
        "Inventory Dimension": "dimension_name",
        "Quality Inspection Template": "quality_inspection_template_name",
        "Shipment Parcel Template": "parcel_template_name",
        "Cheque Print Template": "bank_name",
        "Financial Report Template": "template_name",
        "Journal Entry Template": "template_title",
        "Loyalty Program": "loyalty_program_name",
        "Monthly Distribution": "distribution_id",
        "Payment Term": "payment_term_name",
        "Payment Terms Template": "template_name",
        "Shipping Rule": "label",
        "Tax Category": "title",
        "Tax Withholding Group": "group_name",
        "Terms and Conditions": "title",
        "Letter Head": "letter_head_name",
        "Workflow": "workflow_name",
    }
    fieldname = names.get(doctype)
    return str(fields[fieldname]) if fieldname else _fixture_name(doctype)


def _safe_update(doc: Any, preferred_field: str | None = None) -> str:
    """Exercise native save without mutating a naming, Link, or executable field."""

    meta = doc.meta
    autoname_field = str(meta.autoname or "").removeprefix("field:")
    candidates = list(meta.fields)
    if preferred_field:
        candidates.sort(key=lambda field: field.fieldname != preferred_field)
    for field in candidates:
        if (
            not field.fieldname
            or field.fieldname == autoname_field
            or (field.reqd and field.fieldname != preferred_field)
            or (field.unique and field.fieldname != preferred_field)
            or field.fieldtype
            not in {
                "Check",
                "Int",
                "Float",
                "Currency",
                "Percent",
                "Data",
                "Small Text",
                "Text",
            }
        ):
            continue
        current = doc.get(field.fieldname)
        if field.fieldtype == "Check":
            value = 0 if current else 1
        elif field.fieldtype in {"Int", "Float", "Currency", "Percent"}:
            value = float(current or 0) + 1
            if field.fieldtype == "Int":
                value = int(value)
        else:
            value = f"{current or ''} phase8".strip()
        doc.set(field.fieldname, value)
        doc.save(ignore_permissions=True)
        return str(field.fieldname)
    doc.save(ignore_permissions=True)
    return "controller-save"


def probe_registry_source(doctype: str) -> dict[str, Any]:
    """Create/read/update/delete one source inside a rollback-only transaction."""

    import frappe

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError(
            "policy acceptance probes require a disposable acceptance site"
        )
    scope = policy._load_scope(policy._policy_path())
    source = next(
        (
            item
            for item in scope["sources"]
            if item["name"] == doctype
            and item["classification"] in {"managed", "conditional"}
        ),
        None,
    )
    if source is None:
        raise KeyError(doctype)
    kind, resolved = resolve_builder(source["acceptance"]["fixture_builder"])
    if resolved != doctype:
        raise RuntimeError(f"Acceptance builder mismatch for {doctype}")
    previous_apply_flag = getattr(frappe.flags, "in_letron_policy_apply", False)
    previous_in_test = frappe.in_test
    frappe.flags.in_letron_policy_apply = True
    frappe.in_test = True  # ty: ignore[invalid-assignment]
    try:
        if kind == "native-single":
            doc = frappe.get_single(doctype)
            preferred = SINGLE_UPDATE_FIELDS[doctype]
            if preferred is None:
                doc.save(ignore_permissions=True)
                updated_field = "controller-save"
            else:
                updated_field = _safe_update(doc, preferred)
            readback = frappe.get_single(doctype)
            if readback.get(updated_field) != doc.get(updated_field):
                raise AssertionError(
                    f"Single readback mismatch: {doctype}.{updated_field}"
                )
            return {
                "ok": True,
                "doctype": doctype,
                "structural": "single-update-restore",
            }
        if doctype == "Company":
            company = policy.load_policy()["bootstrap"]["company"]["name"]
            if not frappe.db.exists("Company", company):
                raise AssertionError("bootstrap Company does not exist")
            return {"ok": True, "doctype": doctype, "structural": "bootstrap-readback"}

        prerequisites = _runtime_prerequisites()
        _ensure_probe_prerequisites(prerequisites)
        fields = fixture_fields(doctype, prerequisites)
        name = _document_name(doctype, fields)
        frappe.get_doc({"doctype": doctype, "name": name}).unlock()
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        value = {"doctype": doctype, "name": name, **fields}
        doc = frappe.get_doc(value)
        doc.insert(ignore_permissions=True)
        actual_name = str(doc.name)
        readback = frappe.get_doc(doctype, actual_name)
        if readback.doctype != doctype:
            raise AssertionError(f"Native readback mismatch: {doctype}/{actual_name}")
        preferred = DOCUMENT_UPDATE_FIELDS.get(doctype)
        if doctype in DOCUMENT_UPDATE_FIELDS and preferred is None:
            readback.save(ignore_permissions=True)
            updated_field = "controller-save"
        else:
            updated_field = _safe_update(readback, preferred)
        frappe.delete_doc(doctype, actual_name, ignore_permissions=True, force=True)
        if frappe.db.exists(doctype, actual_name):
            raise AssertionError(f"Native delete residue: {doctype}/{actual_name}")
        return {
            "ok": True,
            "doctype": doctype,
            "name": actual_name,
            "updated_field": updated_field,
            "structural": "create-readback-update-delete",
        }
    finally:
        frappe.db.rollback()
        frappe.clear_cache()
        frappe.flags.in_letron_policy_apply = previous_apply_flag
        frappe.in_test = previous_in_test


def probe_policy_apply_registry(doctypes: list[str] | None = None) -> dict[str, Any]:
    """Apply/readback/idempotency/delete every registry fixture atomically."""

    import tempfile
    from pathlib import Path

    import frappe

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError(
            "policy acceptance probes require a disposable acceptance site"
        )
    prerequisites = _runtime_prerequisites()
    previous_in_test = frappe.in_test
    frappe.in_test = True  # ty: ignore[invalid-assignment]
    paths: list[Path] = []
    try:
        requested = set(doctypes or DOCUMENT_BUILDERS)
        unknown = requested - DOCUMENT_BUILDERS.keys()
        if unknown:
            raise KeyError(", ".join(sorted(unknown)))
        scope = policy._load_scope(policy._policy_path())
        scope_by_name = {item["name"]: item for item in scope["sources"]}
        selected = set(requested)
        pending = list(requested)
        while pending:
            current = pending.pop()
            for dependency in scope_by_name[current]["dependency"]:
                if dependency in DOCUMENT_BUILDERS and dependency not in selected:
                    selected.add(dependency)
                    pending.append(dependency)

        _ensure_probe_prerequisites(prerequisites, include_policy_dependencies=False)
        source = policy.load_policy()
        entries = {
            (str(entry["doctype"]), str(entry["name"])): entry
            for entry in source["documents"]
        }
        for doctype in sorted(selected):
            if doctype == "Company":
                continue
            fields = fixture_fields(doctype, prerequisites)
            name = _document_name(doctype, fields)
            entries[(doctype, name)] = {
                "doctype": doctype,
                "name": name,
                "state": "present",
                "fields": fields,
            }
        if ("Print Settings", "Print Settings") not in entries:
            entries[("Print Settings", "Print Settings")] = {
                "doctype": "Print Settings",
                "name": "Print Settings",
                "state": "present",
                "fields": {},
            }
        bundle = {
            "version": policy.POLICY_VERSION,
            "scope_version": policy.POLICY_SCOPE_VERSION,
            "erpnext_version": source["erpnext_version"],
            "assets": {},
            "bootstrap": source["bootstrap"],
            "documents": policy._sorted_entries(entries.values()),
        }

        def write_bundle(value: Mapping[str, Any], suffix: str) -> Path:
            path = Path(tempfile.gettempdir()) / f"letron-phase8-{suffix}.yaml"
            path.write_text(policy.dump_policy(value), encoding="utf-8", newline="\n")
            paths.append(path)
            return path

        initial_path = write_bundle(bundle, "initial")
        first = policy.apply(initial_path, require_convergence=False)
        canonical = policy.export_current_bundle(initial_path)
        canonical_path = write_bundle(canonical, "canonical")
        second = policy.apply(canonical_path)
        if second["applied"] != 0 or second["drift_count"] != 0:
            raise AssertionError("second registry policy apply was not idempotent")
        if policy.export_current_bundle(canonical_path) != canonical:
            raise AssertionError("registry policy canonical round-trip differs")

        baseline_keys = {
            (base["doctype"], base["name"]) for base in source["documents"]
        }
        absent = dict(source)
        absent["documents"] = list(source["documents"]) + [
            {
                "doctype": entry["doctype"],
                "name": entry["name"],
                "state": "absent",
                "fields": {},
            }
            for entry in canonical["documents"]
            if (entry["doctype"], entry["name"]) not in baseline_keys
            and entry["doctype"] not in SINGLE_BUILDERS
        ]
        absent_path = write_bundle(absent, "absent")
        _unlink_fixture_workflow_state()
        removed = policy.apply(absent_path)
        policy.apply()
        return {
            "ok": True,
            "sources": len(requested),
            "first_applied": first["applied"],
            "second_applied": second["applied"],
            "removed": removed["applied"],
            "roundtrip_diff": 0,
        }
    finally:
        frappe.db.rollback()
        frappe.in_test = previous_in_test
        for path in paths:
            path.unlink(missing_ok=True)
        cleanup_registry_residue()


def _probe_group(doctypes: list[str]) -> dict[str, Any]:
    results = []
    try:
        for doctype in doctypes:
            try:
                results.append(probe_registry_source(doctype))
            except Exception as error:
                raise RuntimeError(
                    f"Policy acceptance failed for {doctype}: {error}"
                ) from error
        return {"ok": True, "passed": len(results), "results": results}
    finally:
        cleanup_registry_residue()


def probe_structural_sources(doctypes: list[str]) -> dict[str, Any]:
    """Run a bounded structural shard supplied by the acceptance runner."""

    unknown = set(doctypes) - (SINGLE_BUILDERS | DOCUMENT_BUILDERS.keys())
    if unknown:
        raise KeyError(", ".join(sorted(unknown)))
    return _probe_group(doctypes)


def _unlink_fixture_workflow_state() -> None:
    """Remove only the unique acceptance state from native controller targets."""

    import frappe

    if frappe.db.has_column("Quotation", "workflow_state"):
        frappe.db.sql(
            """update tabQuotation set workflow_state=null
            where workflow_state like %s""",
            (f"{FIXTURE_PREFIX}%",),
        )


def probe_singles() -> dict[str, Any]:
    return _probe_group(sorted(SINGLE_BUILDERS))


def probe_accounts_and_commercial() -> dict[str, Any]:
    return _probe_group(
        [
            "Company",
            "Fiscal Year",
            "Accounting Dimension",
            "Accounting Dimension Filter",
            "Accounting Period",
            "Bank Transaction Rule",
            "Cheque Print Template",
            "Cost Center Allocation",
            "Dunning Type",
            "Financial Report Template",
            "Item Tax Template",
            "Journal Entry Template",
            "Loyalty Program",
            "Monthly Distribution",
            "Payment Term",
            "Payment Terms Template",
            "Pricing Rule",
            "Promotional Scheme",
            "Purchase Taxes and Charges Template",
            "Sales Taxes and Charges Template",
            "Shipping Rule",
            "Tax Category",
            "Tax Rule",
            "Tax Withholding Category",
            "Tax Withholding Group",
            "Terms and Conditions",
        ]
    )


def probe_buying_and_stock() -> dict[str, Any]:
    return _probe_group(
        [
            "Supplier Scorecard",
            "Inventory Dimension",
            "Putaway Rule",
            "Quality Inspection Template",
            "Shipment Parcel Template",
            "Stock Entry Type",
        ]
    )


def probe_frappe_cross_cutting() -> dict[str, Any]:
    return _probe_group(
        [
            "Role",
            "Role Profile",
            "Workflow State",
            "Workflow Action Master",
            "Custom DocPerm",
            "Assignment Rule",
            "Document Naming Rule",
            "Print Format",
            "Letter Head",
            "Email Template",
            "Notification",
            "Workflow",
        ]
    )


def cleanup_registry_residue() -> dict[str, Any]:
    """Delete only Phase 8 acceptance fixtures in reverse dependency order."""

    import frappe

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError(
            "policy acceptance cleanup requires a disposable acceptance site"
        )
    previous_apply_flag = getattr(frappe.flags, "in_letron_policy_apply", False)
    frappe.flags.in_letron_policy_apply = True
    deleted: list[str] = []
    try:
        _unlink_fixture_workflow_state()
        quotation_names = frappe.get_all(
            "Quotation",
            filters={"party_name": ["like", f"{FIXTURE_PREFIX}%"]},
            pluck="name",
            limit_page_length=0,
        )
        for doctype, fieldname in [
            ("Notification Log", "document_name"),
            ("ToDo", "reference_name"),
        ]:
            for quotation_name in quotation_names:
                for name in frappe.get_all(
                    doctype,
                    filters={fieldname: quotation_name},
                    pluck="name",
                    limit_page_length=0,
                ):
                    frappe.delete_doc(
                        doctype, name, ignore_permissions=True, force=True
                    )
                    deleted.append(f"{doctype}/{name}")
        for name in quotation_names:
            frappe.delete_doc("Quotation", name, ignore_permissions=True, force=True)
            deleted.append(f"Quotation/{name}")
        for name in frappe.get_all(
            "User",
            filters={"name": ["like", "phase8-%@example.invalid"]},
            pluck="name",
            limit_page_length=0,
        ):
            frappe.delete_doc("User", name, ignore_permissions=True, force=True)
            deleted.append(f"User/{name}")
        explicit: list[tuple[str, str]] = [
            ("Inventory Dimension", "Acceptance Inventory Dimension"),
            ("Accounting Dimension", "Acceptance Dimension"),
        ]
        for doctype, name in explicit:
            if frappe.db.exists(doctype, name):
                doc = frappe.get_doc(doctype, name)
                doc.unlock()
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
                deleted.append(f"{doctype}/{name}")
        for name in frappe.get_all(
            "Pricing Rule",
            filters={"title": _fixture_name("Pricing Rule")},
            pluck="name",
            limit_page_length=0,
        ):
            frappe.delete_doc("Pricing Rule", name, ignore_permissions=True, force=True)
            deleted.append(f"Pricing Rule/{name}")
        for doctype in reversed(list(DOCUMENT_BUILDERS)):
            for name in frappe.get_all(
                doctype,
                filters={"name": ["like", "acceptance-local-phase8-%"]},
                pluck="name",
                limit_page_length=0,
            ):
                frappe.get_doc(doctype, name).unlock()
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
                deleted.append(f"{doctype}/{name}")
        for doctype in [
            "Supplier Scorecard Criteria",
            "Quality Inspection Parameter",
            "Supplier",
            "Customer",
            "Item",
            "Customer Group",
            "Territory",
            "Price List",
        ]:
            for name in frappe.get_all(
                doctype,
                filters={"name": ["like", "acceptance-local-phase8-%"]},
                pluck="name",
                limit_page_length=0,
            ):
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
                deleted.append(f"{doctype}/{name}")
        for name in frappe.get_all(
            "Cost Center",
            filters={"name": ["like", "Phase8 Allocation%"]},
            pluck="name",
            limit_page_length=0,
        ):
            frappe.delete_doc("Cost Center", name, ignore_permissions=True, force=True)
            deleted.append(f"Cost Center/{name}")
        frappe.db.commit()
        frappe.clear_cache()
        policy.apply()
        return {"ok": True, "deleted": len(deleted), "documents": deleted}
    finally:
        frappe.flags.in_letron_policy_apply = previous_apply_flag
        frappe.clear_cache()


def acceptance_residue_summary() -> dict[str, Any]:
    """Return exact Phase 8 fixture residue counters without mutating state."""

    import frappe

    queries: dict[str, dict[str, Any]] = {
        "File": {"file_name": ["like", "phase8-%"]},
        "User": {"name": ["like", "phase8-%@example.invalid"]},
        "Quotation": {"party_name": ["like", f"{FIXTURE_PREFIX}%"]},
        "Sales Invoice": {"customer": ["like", f"{FIXTURE_PREFIX}%"]},
        "Purchase Invoice": {"supplier": ["like", f"{FIXTURE_PREFIX}%"]},
        "GL Entry": {"party": ["like", f"{FIXTURE_PREFIX}%"]},
        "Stock Ledger Entry": {"item_code": ["like", f"{FIXTURE_PREFIX}%"]},
        "Letron Event Outbox": {"payload": ["like", f"%{FIXTURE_PREFIX}%"]},
    }
    counts = {
        doctype: frappe.db.count(doctype, filters=filters)
        for doctype, filters in queries.items()
    }
    for doctype in DOCUMENT_BUILDERS:
        counts[doctype] = frappe.db.count(
            doctype, filters={"name": ["like", f"{FIXTURE_PREFIX}%"]}
        )
    counts["File"] += frappe.db.count(
        "File", filters={"folder": "Home/Letron Policy Assets", "is_folder": 0}
    )
    return {
        "ok": not any(counts.values()),
        "acceptance_residue": sum(counts.values()),
        "counts": {key: value for key, value in counts.items() if value},
    }


def probe_asset_lifecycle() -> dict[str, Any]:
    """Verify public/private native File lifecycle and failure compensation."""

    import hashlib
    from pathlib import Path

    import frappe

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError("asset acceptance requires a disposable acceptance site")
    source = policy.load_policy()
    policy_dir = policy._policy_path().parent
    public_source = policy_dir / "assets" / "phase8-public.txt"
    private_source = policy_dir / "assets" / "phase8-private.txt"
    paths: list[Path] = []
    unmanaged_name: str | None = None

    def manifest(
        key: str, source_path: Path, filename: str, privacy: str
    ) -> dict[str, Any]:
        return {
            "source": source_path.name,
            "filename": filename,
            "privacy": privacy,
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }

    def write_bundle(value: Mapping[str, Any], suffix: str) -> Path:
        path = policy_dir / f".phase8-assets-{suffix}.yaml"
        path.write_text(policy.dump_policy(value), encoding="utf-8", newline="\n")
        paths.append(path)
        return path

    try:
        assets = {
            "public": manifest(
                "public", public_source, "phase8-policy-public.txt", "public"
            ),
            "private": manifest(
                "private", private_source, "phase8-policy-private.txt", "private"
            ),
        }
        present = dict(source)
        present["assets"] = assets
        present_path = write_bundle(present, "present")
        created = policy.apply(present_path)
        for key, expected in assets.items():
            name = frappe.db.get_value(
                "File",
                {
                    "folder": policy.POLICY_ASSET_FOLDER,
                    "file_name": expected["filename"],
                },
                "name",
            )
            if not name:
                raise AssertionError(f"native File missing for asset {key}")
            file_doc = frappe.get_doc("File", name)
            expected_url = (
                f"/private/files/{expected['filename']}"
                if expected["privacy"] == "private"
                else f"/files/{expected['filename']}"
            )
            if file_doc.get("file_url") != expected_url:
                raise AssertionError(f"native File URL mismatch for asset {key}")
            if (
                hashlib.sha256(policy._file_content_bytes(file_doc)).hexdigest()
                != expected["sha256"]
            ):
                raise AssertionError(f"native File checksum mismatch for asset {key}")

        conflicting = dict(present)
        conflicting_assets = {key: dict(value) for key, value in assets.items()}
        conflicting_assets["public"] = manifest(
            "public", private_source, "phase8-policy-public.txt", "public"
        )
        conflicting["assets"] = conflicting_assets
        conflict_path = write_bundle(conflicting, "checksum-conflict")
        try:
            policy.apply(conflict_path)
        except policy.PolicyError as error:
            if "checksum" not in str(error):
                raise
        else:
            raise AssertionError("same-filename checksum conflict was accepted")

        unmanaged = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": "phase8-unmanaged.txt",
                "is_private": 0,
                "content": public_source.read_bytes(),
            }
        ).insert(ignore_permissions=True)
        frappe.db.commit()
        unmanaged_name = str(unmanaged.name)
        collision = dict(present)
        collision["assets"] = {
            **assets,
            "collision": manifest(
                "collision", public_source, "phase8-unmanaged.txt", "public"
            ),
        }
        try:
            policy.apply(write_bundle(collision, "collision"))
        except policy.PolicyError as error:
            if "unmanaged File" not in str(error):
                raise
        else:
            raise AssertionError("unmanaged filename collision was accepted")

        invalid = dict(source)
        invalid["assets"] = {
            "traversal": {
                **manifest("traversal", public_source, "traversal.txt", "public"),
                "source": "../phase8-public.txt",
            }
        }
        try:
            write_bundle(invalid, "traversal")
            policy.load_policy(paths[-1])
        except policy.PolicyError as error:
            if "traversal" not in str(error):
                raise
        else:
            raise AssertionError("asset path traversal was accepted")

        removed = policy.apply(write_bundle(source, "removed"))
        if policy._owned_asset_files():
            raise AssertionError("owned native File residue remains after asset delete")
        if not frappe.db.exists("File", unmanaged_name):
            raise AssertionError("unmanaged File was deleted by policy cleanup")

        failure = dict(source)
        failure["assets"] = {
            "rollback": manifest(
                "rollback", public_source, "phase8-policy-rollback.txt", "public"
            )
        }
        failure["documents"] = list(source["documents"]) + [
            {
                "doctype": "Accounting Period",
                "name": _fixture_name("asset rollback period"),
                "state": "present",
                "fields": {
                    "period_name": _fixture_name("asset rollback period"),
                    "start_date": "2042-01-01",
                    "end_date": "2042-12-31",
                    "company": source["bootstrap"]["company"]["name"],
                    "closed_documents": [{"document_type": "Sales Invoice"}],
                },
            }
        ]
        failure_rejected = False
        try:
            policy.apply(write_bundle(failure, "rollback"))
        except (policy.PolicyError, frappe.ValidationError):
            failure_rejected = True
        else:
            raise AssertionError("controller failure injection did not fail")
        if not failure_rejected:
            raise AssertionError("controller failure injection was not observed")
        if frappe.db.exists(
            "File",
            {
                "folder": policy.POLICY_ASSET_FOLDER,
                "file_name": "phase8-policy-rollback.txt",
            },
        ):
            raise AssertionError("rollback native File row remains")
        rollback_path = Path(
            frappe.get_site_path("public", "files", "phase8-policy-rollback.txt")
        )
        if rollback_path.exists():
            raise AssertionError("rollback asset file remains")
        return {
            "ok": True,
            "created": created["applied"],
            "removed": removed["applied"],
            "public_private": 2,
            "checksum_conflict": "rejected",
            "traversal": "rejected",
            "collision": "rejected",
            "rollback": "byte-clean",
        }
    finally:
        try:
            policy.apply()
        finally:
            if unmanaged_name and frappe.db.exists("File", unmanaged_name):
                frappe.delete_doc(
                    "File", unmanaged_name, ignore_permissions=True, force=True
                )
                frappe.db.commit()
            for path in paths:
                path.unlink(missing_ok=True)


def probe_payment_terms_effect() -> dict[str, Any]:
    """Prove the native template produces a balanced payment schedule."""

    import frappe

    if not __import__(
        "letron_api.policy", fromlist=["_is_test_runtime"]
    )._is_test_runtime():
        raise RuntimeError("controller-effect probes require an acceptance runtime")
    prerequisites = _runtime_prerequisites()
    previous_in_test = frappe.in_test
    try:
        _ensure_probe_prerequisites(prerequisites)
        template = _fixture_name("Payment Terms Template")
        frappe.get_doc(
            {
                "doctype": "Payment Terms Template",
                **fixture_fields("Payment Terms Template", prerequisites),
            }
        ).insert(ignore_permissions=True)
        order: Any = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "company": prerequisites["company"],
                "currency": "VND",
                "conversion_rate": 1,
                "transaction_date": frappe.utils.nowdate(),
                "payment_terms_template": template,
                "grand_total": 125000,
                "base_grand_total": 125000,
            }
        )
        order.set_payment_schedule()
        if len(order.payment_schedule) != 1:
            raise AssertionError(
                "Payment Terms Template did not create one schedule row"
            )
        row = order.payment_schedule[0]
        if float(row.invoice_portion) != 100 or float(row.payment_amount) != 125000:
            raise AssertionError(
                "Payment Terms Template produced an unbalanced schedule"
            )
        return {"ok": True, "rows": 1, "portion": 100, "amount": 125000}
    finally:
        frappe.db.rollback()
        frappe.in_test = previous_in_test
        cleanup_registry_residue()


def probe_failure_rollback(step: str) -> dict[str, Any]:
    """Inject one apply-boundary failure and prove transaction compensation."""

    import copy
    import hashlib
    from pathlib import Path

    import frappe

    from letron_api import policy

    supported = {
        "after-assets",
        "after-documents",
        "after-deletes",
        "before-cache",
        "before-commit",
    }
    if step not in supported:
        raise ValueError(f"unsupported failure step: {step}")
    if not policy._is_test_runtime():
        raise RuntimeError("failure rollback probe requires an acceptance runtime")

    source_path = policy._policy_path()
    source_bytes = source_path.read_bytes()
    source = policy.load_policy()
    policy_dir = source_path.parent
    asset_source = policy_dir / "assets" / "phase8-public.txt"
    filename = "phase8-policy-rollback.txt"
    fixture_name = _fixture_name("Payment Term")
    temporary_paths: list[Path] = []
    cache = policy._frappe().cache()
    previous_cache = cache.get_value(policy.POLICY_STATUS_CACHE_KEY)
    expected_cache = previous_cache

    def bundle(state: str) -> dict[str, Any]:
        value = copy.deepcopy(source)
        value["assets"] = (
            {
                "rollback": {
                    "source": asset_source.name,
                    "filename": filename,
                    "privacy": "public",
                    "sha256": hashlib.sha256(asset_source.read_bytes()).hexdigest(),
                }
            }
            if state == "present"
            else {}
        )
        value["documents"].append(
            {
                "doctype": "Payment Term",
                "name": fixture_name,
                "state": state,
                "fields": (
                    fixture_fields("Payment Term", {}) if state == "present" else {}
                ),
            }
        )
        return value

    def write_bundle(value: Mapping[str, Any], suffix: str) -> Path:
        path = policy_dir / f".phase8-rollback-{suffix}.yaml"
        path.write_text(policy.dump_policy(value), encoding="utf-8", newline="\n")
        temporary_paths.append(path)
        return path

    def state() -> tuple[bool, bool, bytes | None]:
        document_exists = bool(frappe.db.exists("Payment Term", fixture_name))
        file_name = frappe.db.get_value(
            "File",
            {"folder": policy.POLICY_ASSET_FOLDER, "file_name": filename},
            "name",
        )
        if not file_name:
            return document_exists, False, None
        file_doc = frappe.get_doc("File", file_name)
        return document_exists, True, policy._file_content_bytes(file_doc)

    expected = (False, False, None)
    try:
        cleanup_registry_residue()
        if step == "after-deletes":
            policy.apply(write_bundle(bundle("present"), "delete-setup"))
            expected = state()
            expected_cache = cache.get_value(policy.POLICY_STATUS_CACHE_KEY)
            target = write_bundle(bundle("absent"), "delete")
        else:
            target = write_bundle(bundle("present"), step)
        try:
            policy.apply(target, _failure_step=step)
        except policy.PolicyError as error:
            if "Injected policy acceptance failure" not in str(error):
                raise
        else:
            raise AssertionError(f"failure injection did not fire at {step}")

        actual = state()
        if actual != expected:
            raise AssertionError(
                f"rollback mismatch at {step}: expected={expected[:2]} actual={actual[:2]}"
            )
        if source_path.read_bytes() != source_bytes:
            raise AssertionError("production policy YAML changed during rollback probe")
        if cache.get_value(policy.POLICY_STATUS_CACHE_KEY) != expected_cache:
            raise AssertionError("policy status cache was not restored byte-equivalent")
        return {
            "ok": True,
            "step": step,
            "document_restored": actual[0] == expected[0],
            "asset_restored": actual[1:] == expected[1:],
            "yaml_unchanged": True,
            "cache_restored": True,
        }
    finally:
        frappe.db.rollback()
        if frappe.db.exists("Payment Term", fixture_name):
            frappe.delete_doc(
                "Payment Term", fixture_name, ignore_permissions=True, force=True
            )
        for file_name in frappe.get_all(
            "File",
            filters={"folder": policy.POLICY_ASSET_FOLDER, "file_name": filename},
            pluck="name",
            limit_page_length=0,
        ):
            frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
        public_path = Path(frappe.get_site_path("public", "files", filename))
        public_path.unlink(missing_ok=True)
        frappe.db.commit()
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        cleanup_registry_residue()


def probe_pricing_shipping_effects() -> dict[str, Any]:
    """Prove native pricing lookup and shipping charge materialization."""

    import frappe
    from erpnext.accounts.doctype.pricing_rule.pricing_rule import (  # ty: ignore[unresolved-import]
        apply_pricing_rule,
    )

    prerequisites = _runtime_prerequisites()
    try:
        _ensure_probe_prerequisites(prerequisites)
        pricing_fields = fixture_fields("Pricing Rule", prerequisites)
        pricing_fields["valid_from"] = "2020-01-01"
        pricing_fields["valid_upto"] = "2099-12-31"
        pricing = frappe.get_doc({"doctype": "Pricing Rule", **pricing_fields}).insert(
            ignore_permissions=True
        )
        result = apply_pricing_rule(
            {
                "doctype": "Sales Order",
                "items": [
                    {
                        "doctype": "Sales Order Item",
                        "name": "new-sales-order-item-1",
                        "parent": "new-sales-order-1",
                        "parenttype": "Sales Order",
                        "item_code": prerequisites["item"],
                        "qty": 1,
                        "uom": prerequisites["uom"],
                        "price_list_rate": 100000,
                        "conversion_factor": 1,
                    }
                ],
                "company": prerequisites["company"],
                "currency": "VND",
                "conversion_rate": 1,
                "price_list_currency": "VND",
                "plc_conversion_rate": 1,
                "transaction_date": frappe.utils.nowdate(),
                "selling": 1,
                "ignore_pricing_rule": 0,
            }
        )[0]
        if float(result.get("discount_percentage") or 0) != 5:
            raise AssertionError(
                f"Pricing Rule did not return the configured 5% discount: {dict(result)}"
            )

        shipping_fields = fixture_fields("Shipping Rule", prerequisites)
        shipping: Any = frappe.get_doc(
            {"doctype": "Shipping Rule", **shipping_fields}
        ).insert(ignore_permissions=True)
        order: Any = frappe.get_doc(
            {
                "doctype": "Sales Order",
                "company": prerequisites["company"],
                "currency": "VND",
                "company_currency": "VND",
                "conversion_rate": 1,
                "base_net_total": 100000,
                "net_total": 100000,
                "taxes": [],
            }
        )
        shipping.apply(order)
        if len(order.taxes) != 1 or float(order.taxes[0].tax_amount) != 1000:
            raise AssertionError("Shipping Rule did not add the configured charge")
        return {
            "ok": True,
            "pricing_rule": str(pricing.name),
            "discount_percentage": 5,
            "shipping_rule": str(shipping.name),
            "shipping_amount": 1000,
        }
    finally:
        frappe.db.rollback()
        cleanup_registry_residue()


def probe_stock_buying_effects() -> dict[str, Any]:
    """Prove Stock Entry purpose and Quality Template parameter propagation."""

    import frappe

    prerequisites = _runtime_prerequisites()
    previous_in_test = frappe.in_test
    frappe.in_test = True  # ty: ignore[invalid-assignment]
    try:
        _ensure_probe_prerequisites(prerequisites)
        stock_type = frappe.get_doc(
            {
                "doctype": "Stock Entry Type",
                "name": _fixture_name("Stock Entry Type"),
                **fixture_fields("Stock Entry Type", prerequisites),
            }
        ).insert(ignore_permissions=True)
        stock_entry: Any = frappe.get_doc(
            {"doctype": "Stock Entry", "stock_entry_type": stock_type.name}
        )
        stock_entry.set_purpose_for_stock_entry()
        if stock_entry.purpose != "Material Transfer":
            raise AssertionError("Stock Entry Type did not set native purpose")

        template = frappe.get_doc(
            {
                "doctype": "Quality Inspection Template",
                **fixture_fields("Quality Inspection Template", prerequisites),
            }
        ).insert(ignore_permissions=True)
        inspection: Any = frappe.get_doc(
            {
                "doctype": "Quality Inspection",
                "inspection_type": "Incoming",
                "item_code": prerequisites["item"],
                "quality_inspection_template": template.name,
            }
        )
        inspection.get_item_specification_details()
        if (
            not inspection.readings
            or inspection.readings[0].specification
            != prerequisites["quality_parameter"]
        ):
            raise AssertionError(
                "Quality Inspection Template did not populate readings"
            )
        scorecard: Any = frappe.get_doc(
            {
                "doctype": "Supplier Scorecard",
                **fixture_fields("Supplier Scorecard", prerequisites),
            }
        ).insert(ignore_permissions=True)
        if not scorecard.criteria or float(scorecard.criteria[0].weight) != 100:
            raise AssertionError(
                "Supplier Scorecard criteria were not accepted by controller"
            )
        return {
            "ok": True,
            "purpose": stock_entry.purpose,
            "readings": 1,
            "scorecard": str(scorecard.name),
        }
    finally:
        frappe.db.rollback()
        frappe.in_test = previous_in_test
        cleanup_registry_residue()


def probe_tax_effect_rate(rate: int = 10) -> dict[str, Any]:
    """Calculate and post Sales/Purchase tax through native invoice controllers."""

    import frappe
    from erpnext.accounts.doctype.tax_rule.tax_rule import (  # ty: ignore[unresolved-import]
        get_tax_template,
    )

    if rate not in {0, 5, 8, 10}:
        raise ValueError("tax acceptance rate must be one of 0, 5, 8, 10")
    prerequisites = _runtime_prerequisites()
    vouchers: list[tuple[str, str]] = []
    expected_tax = 100000 * rate / 100
    try:
        _ensure_probe_prerequisites(prerequisites)
        suffix = f"{rate}-{frappe.generate_hash(length=6).lower()}"
        sales = frappe.get_doc(
            {
                "doctype": "Sales Taxes and Charges Template",
                "title": f"Acceptance Sales Tax {suffix}",
                "company": prerequisites["company"],
                "disabled": 0,
                "taxes": [
                    {
                        "charge_type": "On Net Total",
                        "account_head": prerequisites["tax_account"],
                        "description": f"Tax {rate}%",
                        "cost_center": prerequisites["cost_center"],
                        "rate": rate,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        purchase = frappe.get_doc(
            {
                "doctype": "Purchase Taxes and Charges Template",
                "title": f"Acceptance Purchase Tax {suffix}",
                "company": prerequisites["company"],
                "disabled": 0,
                "taxes": [
                    {
                        "category": "Total",
                        "add_deduct_tax": "Add",
                        "charge_type": "On Net Total",
                        "account_head": prerequisites["tax_account"],
                        "description": f"Tax {rate}%",
                        "cost_center": prerequisites["cost_center"],
                        "rate": rate,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        item_template: Any = frappe.get_doc(
            {
                "doctype": "Item Tax Template",
                "title": f"Acceptance Item Tax {suffix}",
                "company": prerequisites["company"],
                "taxes": [{"tax_type": prerequisites["tax_account"], "tax_rate": rate}],
            }
        ).insert(ignore_permissions=True)
        if float(item_template.taxes[0].tax_rate) != rate:
            raise AssertionError(
                "Item Tax Template did not preserve the configured rate"
            )

        category = frappe.get_doc(
            {
                "doctype": "Tax Category",
                "title": f"Acceptance Tax Category {suffix}",
                "disabled": 0,
            }
        ).insert(ignore_permissions=True)
        rule = frappe.get_doc(
            {
                "doctype": "Tax Rule",
                "tax_type": "Sales",
                "company": prerequisites["company"],
                "tax_category": category.name,
                "sales_tax_template": sales.name,
                "from_date": "2020-01-01",
                "to_date": "2099-12-31",
            }
        ).insert(ignore_permissions=True)
        selected = get_tax_template(
            frappe.utils.nowdate(),
            {
                "tax_type": "Sales",
                "company": prerequisites["company"],
                "tax_category": category.name,
            },
        )
        if selected != sales.name:
            raise AssertionError(
                f"Tax Rule selected {selected!r}, expected {sales.name!r}"
            )

        sales_invoice: Any = frappe.get_doc(
            {
                "doctype": "Sales Invoice",
                "company": prerequisites["company"],
                "customer": prerequisites["customer"],
                "posting_date": frappe.utils.nowdate(),
                "due_date": frappe.utils.nowdate(),
                "currency": "VND",
                "conversion_rate": 1,
                "selling_price_list": prerequisites["selling_price_list"],
                "price_list_currency": "VND",
                "plc_conversion_rate": 1,
                "taxes_and_charges": sales.name,
                "items": [
                    {
                        "item_code": prerequisites["tax_item"],
                        "qty": 1,
                        "rate": 100000,
                        "income_account": prerequisites["income_account"],
                        "cost_center": prerequisites["cost_center"],
                    }
                ],
            }
        )
        sales_invoice.append_taxes_from_master()
        sales_invoice.insert(ignore_permissions=True)
        vouchers.append(("Sales Invoice", str(sales_invoice.name)))
        if float(sales_invoice.total_taxes_and_charges) != expected_tax:
            raise AssertionError("Sales Invoice tax calculation mismatch")
        sales_invoice.submit()
        sales_tax_gl = frappe.db.get_value(
            "GL Entry",
            {
                "voucher_type": "Sales Invoice",
                "voucher_no": sales_invoice.name,
                "account": prerequisites["tax_account"],
                "is_cancelled": 0,
            },
            "credit",
        )
        if float(sales_tax_gl or 0) != expected_tax:
            raise AssertionError("Sales Invoice tax GL mismatch")

        purchase_invoice: Any = frappe.get_doc(
            {
                "doctype": "Purchase Invoice",
                "company": prerequisites["company"],
                "supplier": prerequisites["supplier"],
                "posting_date": frappe.utils.nowdate(),
                "due_date": frappe.utils.nowdate(),
                "bill_no": f"P8-{suffix}",
                "bill_date": frappe.utils.nowdate(),
                "currency": "VND",
                "conversion_rate": 1,
                "buying_price_list": prerequisites["buying_price_list"],
                "price_list_currency": "VND",
                "plc_conversion_rate": 1,
                "taxes_and_charges": purchase.name,
                "items": [
                    {
                        "item_code": prerequisites["tax_item"],
                        "qty": 1,
                        "rate": 100000,
                        "expense_account": prerequisites["expense_account"],
                        "cost_center": prerequisites["cost_center"],
                    }
                ],
            }
        )
        purchase_invoice.append_taxes_from_master()
        purchase_invoice.insert(ignore_permissions=True)
        vouchers.append(("Purchase Invoice", str(purchase_invoice.name)))
        if float(purchase_invoice.total_taxes_and_charges) != expected_tax:
            raise AssertionError("Purchase Invoice tax calculation mismatch")
        purchase_invoice.submit()
        purchase_tax_gl = frappe.db.get_value(
            "GL Entry",
            {
                "voucher_type": "Purchase Invoice",
                "voucher_no": purchase_invoice.name,
                "account": prerequisites["tax_account"],
                "is_cancelled": 0,
            },
            "debit",
        )
        if float(purchase_tax_gl or 0) != expected_tax:
            raise AssertionError("Purchase Invoice tax GL mismatch")
        return {
            "ok": True,
            "rate": rate,
            "tax": expected_tax,
            "sales_gl": float(sales_tax_gl or 0),
            "purchase_gl": float(purchase_tax_gl or 0),
            "tax_rule": str(rule.name),
        }
    finally:
        for doctype, name in reversed(vouchers):
            if frappe.db.exists(doctype, name):
                doc = frappe.get_doc(doctype, name)
                if doc.docstatus == 1:
                    doc.cancel()
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        frappe.db.rollback()
        cleanup_registry_residue()


def probe_configured_tax_policy() -> dict[str, Any]:
    """Read back configured tax categories/rules and verify native selection."""

    import frappe
    from erpnext.accounts.doctype.tax_rule.tax_rule import (  # ty: ignore[unresolved-import]
        get_tax_template,
    )

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError("configured tax policy probe requires a disposable acceptance site")

    company = policy.load_policy()["bootstrap"]["company"]["name"]
    software_category = "Domestic Software - Non-VAT - LTVN"
    hosting_category = "Domestic Hosting - LTVN"
    software_sales = "Vietnam Software Non-VAT - LTVN"
    standard_sales = "Vietnam Tax - LTVN"
    expected = {
        "Tax Category": [software_category, hosting_category, "Domestic Transport - LTVN"],
        "Sales Taxes and Charges Template": [software_sales, standard_sales],
        "Purchase Taxes and Charges Template": [software_sales, standard_sales],
        "Item Tax Template": [software_sales],
        "Tax Rule": [
            "Domestic Software Sales - LTVN",
            "Domestic Software Purchase - LTVN",
            "Domestic Hosting Sales - LTVN",
            "Domestic Hosting Purchase - LTVN",
            "Domestic Transport Sales - LTVN",
            "Domestic Transport Purchase - LTVN",
        ],
    }
    missing = [
        f"{doctype}:{name}"
        for doctype, names in expected.items()
        for name in names
        if not frappe.db.exists(doctype, name)
    ]
    if missing:
        raise AssertionError("configured tax policy records missing: " + ", ".join(missing))

    item_template = frappe.get_doc("Item Tax Template", software_sales)
    item_rows = item_template.get("taxes") or []
    if len(item_rows) != 1:
        raise AssertionError("software Item Tax Template must contain one detail row")
    item_row = item_rows[0]
    if str(item_row.tax_type) != "VAT - LTVN" or float(item_row.tax_rate or 0) != 0.0:
        raise AssertionError("software Item Tax Template must use zero tax rate")
    if int(item_row.not_applicable or 0) != 1:
        raise AssertionError("software Item Tax Template must mark VAT as not applicable")

    for doctype in ("Sales Taxes and Charges Template", "Purchase Taxes and Charges Template"):
        if frappe.get_doc(doctype, software_sales).get("taxes"):
            raise AssertionError(f"{doctype} software template must have no tax rows")

    today = frappe.utils.nowdate()
    selected = {
        "software_sales": get_tax_template(
            today,
            {"tax_type": "Sales", "company": company, "tax_category": software_category},
        ),
        "software_purchase": get_tax_template(
            today,
            {"tax_type": "Purchase", "company": company, "tax_category": software_category},
        ),
        "hosting_sales": get_tax_template(
            today,
            {"tax_type": "Sales", "company": company, "tax_category": hosting_category},
        ),
        "hosting_purchase": get_tax_template(
            today,
            {"tax_type": "Purchase", "company": company, "tax_category": hosting_category},
        ),
    }
    assert selected == {
        "software_sales": software_sales,
        "software_purchase": software_sales,
        "hosting_sales": standard_sales,
        "hosting_purchase": standard_sales,
    }
    return {"ok": True, "company": company, "selected": selected}


def probe_configured_tax_invoice_effects() -> dict[str, Any]:
    """Submit policy-routed Sales/Purchase Invoices and verify VAT GL amounts."""

    import frappe
    from erpnext.accounts.doctype.tax_rule.tax_rule import get_tax_template  # type: ignore[unresolved-import]

    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError("configured tax invoice probe requires a disposable acceptance site")

    prerequisites = _runtime_prerequisites()
    company = prerequisites["company"]
    today = frappe.utils.nowdate()
    routes = {
        "software": ("Domestic Software - Non-VAT - LTVN", 0.0),
        "hosting": ("Domestic Hosting - LTVN", 10000.0),
        "transport": ("Domestic Transport - LTVN", 10000.0),
    }
    created: list[tuple[str, str]] = []
    fiscal_year_name: str | None = None
    original_po_required: Any = None
    original_pr_required: Any = None
    observed: dict[str, dict[str, float]] = {}
    try:
        _ensure_probe_prerequisites(prerequisites)
        # This probe isolates VAT calculation. The configured policy may require
        # PO/PR for normal purchasing, so temporarily bypass only those
        # controller gates inside the disposable transaction and restore them.
        original_po_required = frappe.db.get_single_value("Buying Settings", "po_required")
        original_pr_required = frappe.db.get_single_value("Buying Settings", "pr_required")
        frappe.db.set_single_value("Buying Settings", "po_required", "No")
        frappe.db.set_single_value("Buying Settings", "pr_required", "No")
        fiscal_year_name = f"Acceptance FY {today[:4]}-{frappe.generate_hash(length=6).upper()}"
        fiscal_year = frappe.get_doc(
            {
                "doctype": "Fiscal Year",
                "year": fiscal_year_name,
                "year_start_date": f"{today[:4]}-01-01",
                "year_end_date": f"{today[:4]}-12-31",
                "disabled": 0,
                "companies": [{"company": company}],
            }
        ).insert(ignore_permissions=True)
        for label, (category, expected_tax) in routes.items():
            sales_template = get_tax_template(
                today, {"tax_type": "Sales", "company": company, "tax_category": category}
            )
            purchase_template = get_tax_template(
                today, {"tax_type": "Purchase", "company": company, "tax_category": category}
            )
            sales_invoice = frappe.get_doc(
                {
                    "doctype": "Sales Invoice",
                    "company": company,
                    "customer": prerequisites["customer"],
                    "posting_date": today,
                    "due_date": today,
                    "currency": "VND",
                    "conversion_rate": 1,
                    "selling_price_list": prerequisites["selling_price_list"],
                    "price_list_currency": "VND",
                    "plc_conversion_rate": 1,
                    "tax_category": category,
                    "taxes_and_charges": sales_template,
                    "items": [{
                        "item_code": prerequisites["tax_item"],
                        "qty": 1,
                        "rate": 100000,
                        "income_account": prerequisites["income_account"],
                        "cost_center": prerequisites["cost_center"],
                    }],
                }
            )
            sales_invoice.append_taxes_from_master()
            sales_invoice.insert(ignore_permissions=True)
            sales_invoice.submit()
            created.append(("Sales Invoice", str(sales_invoice.name)))
            sales_gl = float(frappe.db.get_value(
                "GL Entry",
                {"voucher_type": "Sales Invoice", "voucher_no": sales_invoice.name,
                 "account": prerequisites["tax_account"], "is_cancelled": 0},
                "credit",
            ) or 0)

            purchase_invoice = frappe.get_doc(
                {
                    "doctype": "Purchase Invoice",
                    "company": company,
                    "supplier": prerequisites["supplier"],
                    "posting_date": today,
                    "due_date": today,
                    "bill_no": f"POLICY-{label}-{frappe.generate_hash(length=6).upper()}",
                    "bill_date": today,
                    "currency": "VND",
                    "conversion_rate": 1,
                    "buying_price_list": prerequisites["buying_price_list"],
                    "price_list_currency": "VND",
                    "plc_conversion_rate": 1,
                    "tax_category": category,
                    "taxes_and_charges": purchase_template,
                    "items": [{
                        "item_code": prerequisites["tax_item"],
                        "qty": 1,
                        "rate": 100000,
                        "expense_account": prerequisites["expense_account"],
                        "cost_center": prerequisites["cost_center"],
                    }],
                }
            )
            purchase_invoice.append_taxes_from_master()
            purchase_invoice.insert(ignore_permissions=True)
            purchase_invoice.submit()
            created.append(("Purchase Invoice", str(purchase_invoice.name)))
            purchase_gl = float(frappe.db.get_value(
                "GL Entry",
                {"voucher_type": "Purchase Invoice", "voucher_no": purchase_invoice.name,
                 "account": prerequisites["tax_account"], "is_cancelled": 0},
                "debit",
            ) or 0)

            if float(sales_invoice.total_taxes_and_charges or 0) != expected_tax:
                raise AssertionError(f"{label} Sales Invoice tax mismatch")
            if float(purchase_invoice.total_taxes_and_charges or 0) != expected_tax:
                raise AssertionError(f"{label} Purchase Invoice tax mismatch")
            if sales_gl != expected_tax or purchase_gl != expected_tax:
                raise AssertionError(f"{label} VAT GL mismatch")
            observed[label] = {"sales_tax": float(sales_invoice.total_taxes_and_charges),
                               "purchase_tax": float(purchase_invoice.total_taxes_and_charges),
                               "sales_gl": sales_gl, "purchase_gl": purchase_gl}
        return {"ok": True, "observed": observed}
    finally:
        for doctype, name in reversed(created):
            if frappe.db.exists(doctype, name):
                doc = frappe.get_doc(doctype, name)
                if doc.docstatus == 1:
                    doc.cancel()
        if fiscal_year_name and frappe.db.exists("Fiscal Year", fiscal_year_name):
            frappe.delete_doc("Fiscal Year", fiscal_year_name, ignore_permissions=True, force=True)
        if original_po_required is not None:
            frappe.db.set_single_value("Buying Settings", "po_required", original_po_required)
        if original_pr_required is not None:
            frappe.db.set_single_value("Buying Settings", "pr_required", original_pr_required)


def probe_configured_accounting_period() -> dict[str, Any]:
    """Verify native Accounting Period behavior for the policy-owned period."""

    import frappe
    from letron_api import policy

    if not policy._is_test_runtime():
        raise RuntimeError("accounting period probe requires a disposable acceptance site")
    expected_name = "FY 2026 - LTVN"
    if not frappe.db.exists("Accounting Period", expected_name):
        raise AssertionError(f"configured accounting period missing: {expected_name}")
    doc = frappe.get_doc("Accounting Period", expected_name)
    if {
        "period_name": doc.period_name,
        "start_date": str(doc.start_date),
        "end_date": str(doc.end_date),
        "company": doc.company,
        "disabled": int(doc.disabled or 0),
        "exempted_role": doc.exempted_role,
    } != {
        "period_name": expected_name,
        "start_date": "2026-01-01",
        "end_date": "2026-08-14",
        "company": "Letron Việt Nam",
        "disabled": 0,
        "exempted_role": None,
    }:
        raise AssertionError("Accounting Period native fields differ from policy")
    closed_documents = {
        str(row.document_type): int(row.closed or 0) for row in (doc.closed_documents or [])
    }
    expected_documents = {
        "Sales Invoice", "Purchase Invoice", "Journal Entry", "Payment Entry", "Purchase Receipt"
    }
    if set(closed_documents) != expected_documents or any(closed_documents.values()):
        raise AssertionError("Accounting Period closed_documents differ from policy")

    from types import SimpleNamespace

    from erpnext.accounts.doctype.accounting_period.accounting_period import (
        ClosedAccountingPeriod,
        validate_accounting_period_on_doc_save,
    )

    sales_invoice_row = next(
        row for row in doc.closed_documents if row.document_type == "Sales Invoice"
    )
    in_period_doc = SimpleNamespace(
        doctype="Sales Invoice",
        company=doc.company,
        posting_date="2026-08-14",
    )
    outside_period_doc = SimpleNamespace(
        doctype="Sales Invoice",
        company=doc.company,
        posting_date="2025-12-31",
    )

    # Policy leaves the configured documents open: an in-period document must pass.
    validate_accounting_period_on_doc_save(in_period_doc)

    # Accounting Period is a closing control, not a global date-range validator:
    # an outside-period document is not blocked by this hook.
    validate_accounting_period_on_doc_save(outside_period_doc)

    original_closed = int(sales_invoice_row.closed or 0)
    try:
        frappe.db.set_value("Closed Document", sales_invoice_row.name, "closed", 1)
        try:
            validate_accounting_period_on_doc_save(in_period_doc)
        except ClosedAccountingPeriod:
            pass
        else:
            raise AssertionError("closed Sales Invoice was not blocked inside the period")

        # No exempted_role is configured, so there is no role-based bypass.
        if doc.exempted_role is not None:
            raise AssertionError("Accounting Period unexpectedly has an exempted_role")
    finally:
        frappe.db.set_value("Closed Document", sales_invoice_row.name, "closed", original_closed)

    return {
        "ok": True,
        "period_name": expected_name,
        "closed_documents": closed_documents,
        "behavior": {
            "in_period_open_allowed": True,
            "outside_period_not_blocked_by_closing_hook": True,
            "in_period_closed_sales_invoice_blocked": True,
            "exempted_role": None,
        },
    }


def _make_effect_quotation(prerequisites: Mapping[str, str]) -> Any:
    import frappe

    return frappe.get_doc(
        {
            "doctype": "Quotation",
            "quotation_to": "Customer",
            "party_name": prerequisites["customer"],
            "company": prerequisites["company"],
            "transaction_date": frappe.utils.nowdate(),
            "valid_till": frappe.utils.add_days(frappe.utils.nowdate(), 7),
            "currency": "VND",
            "conversion_rate": 1,
            "selling_price_list": prerequisites["selling_price_list"],
            "price_list_currency": "VND",
            "plc_conversion_rate": 1,
            "ignore_pricing_rule": 1,
            "items": [
                {
                    "item_code": prerequisites["tax_item"],
                    "qty": 1,
                    "rate": 100000,
                    "price_list_rate": 100000,
                    "income_account": prerequisites["income_account"],
                    "cost_center": prerequisites["cost_center"],
                }
            ],
        }
    )


def probe_cross_cutting_effects(effect: str = "render") -> dict[str, Any]:
    """Run one bounded Frappe cross-cutting controller-effect shard."""

    import frappe

    prerequisites = _runtime_prerequisites()
    previous_in_test = frappe.in_test
    frappe.in_test = True  # ty: ignore[invalid-assignment]
    try:
        _ensure_probe_prerequisites(prerequisites)
        if effect == "render":
            quotation = _make_effect_quotation(prerequisites).insert(
                ignore_permissions=True
            )
            print_format = frappe.get_doc(
                {
                    "doctype": "Print Format",
                    "name": _fixture_name("Print Format"),
                    **fixture_fields("Print Format", prerequisites),
                }
            ).insert(ignore_permissions=True)
            letter_head = frappe.get_doc(
                {
                    "doctype": "Letter Head",
                    "name": _fixture_name("Letter Head"),
                    **fixture_fields("Letter Head", prerequisites),
                }
            ).insert(ignore_permissions=True)
            email_template: Any = frappe.get_doc(
                {
                    "doctype": "Email Template",
                    "name": _fixture_name("Email Template"),
                    **fixture_fields("Email Template", prerequisites),
                }
            ).insert(ignore_permissions=True)
            from frappe.utils.print_utils import get_print

            rendered = get_print(
                "Quotation",
                quotation.name,
                print_format=print_format.name,
                letterhead=letter_head.name,
            )
            if str(quotation.name) not in rendered:
                raise AssertionError("Print Format did not render the native document")
            formatted = email_template.get_formatted_email(quotation.as_dict())
            if (
                str(quotation.name) not in formatted["subject"]
                or str(quotation.name) not in formatted["message"]
            ):
                raise AssertionError("Email Template did not render subject/message")
            return {
                "ok": True,
                "effect": effect,
                "print_format": str(print_format.name),
                "letter_head": str(letter_head.name),
                "email_template": str(email_template.name),
            }

        if effect == "naming":
            prefix = f"P8-{frappe.generate_hash(length=5).upper()}-"
            series_before = frappe.db.sql(
                "select current from tabSeries where name=%s", (prefix,), pluck=True
            )
            rule_fields = fixture_fields("Document Naming Rule", prerequisites)
            rule_fields.update({"prefix": prefix, "disabled": 0})
            rule = frappe.get_doc(
                {"doctype": "Document Naming Rule", **rule_fields}
            ).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="Document Naming Rule")
            quotation = _make_effect_quotation(prerequisites).insert(
                ignore_permissions=True
            )
            if not str(quotation.name).startswith(prefix):
                raise AssertionError("Document Naming Rule did not generate the prefix")
            series_after = frappe.db.sql(
                "select current from tabSeries where name=%s", (prefix,), pluck=True
            )
            if series_after != series_before:
                raise AssertionError(
                    "Document Naming Rule unexpectedly changed tabSeries"
                )
            return {
                "ok": True,
                "effect": effect,
                "name": str(quotation.name),
                "rule": str(rule.name),
                "tab_series_unchanged": True,
            }
        if effect == "notification_assignment":
            notification_user = (
                f"phase8-notify-{frappe.generate_hash(length=6)}@example.invalid"
            )
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": notification_user,
                    "first_name": "Phase8 Notification",
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "roles": [{"role": "System Manager"}],
                }
            ).insert(ignore_permissions=True)
            quotation = _make_effect_quotation(prerequisites).insert(
                ignore_permissions=True
            )
            assignment_fields = fixture_fields("Assignment Rule", prerequisites)
            assignment_fields.update(
                {
                    "disabled": 0,
                    "assignment_days": [
                        {"day": frappe.utils.now_datetime().strftime("%A")}
                    ],
                }
            )
            assignment = frappe.get_doc(
                {
                    "doctype": "Assignment Rule",
                    "name": _fixture_name("Assignment Rule"),
                    **assignment_fields,
                }
            ).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="Assignment Rule")
            from frappe.automation.doctype.assignment_rule.assignment_rule import (
                apply as apply_assignment_rules,
            )

            apply_assignment_rules(doc=quotation)
            todo = frappe.db.get_value(
                "ToDo",
                {
                    "reference_type": "Quotation",
                    "reference_name": quotation.name,
                    "allocated_to": "Administrator",
                    "status": "Open",
                },
                "name",
            )
            if not todo:
                raise AssertionError("Assignment Rule did not create a native ToDo")

            notification_fields = fixture_fields("Notification", prerequisites)
            notification_fields.update(
                {
                    "enabled": 1,
                    "recipients": [{"receiver_by_role": "System Manager"}],
                }
            )
            notification: Any = frappe.get_doc(
                {
                    "doctype": "Notification",
                    "name": _fixture_name("Notification"),
                    **notification_fields,
                }
            ).insert(ignore_permissions=True)
            notification.send(quotation)
            notification_log = frappe.db.get_value(
                "Notification Log",
                {
                    "document_type": "Quotation",
                    "document_name": quotation.name,
                    "for_user": notification_user,
                },
                "name",
            )
            if not notification_log:
                raise AssertionError(
                    "Notification did not create a native Notification Log"
                )
            return {
                "ok": True,
                "effect": effect,
                "assignment_rule": str(assignment.name),
                "todo": str(todo),
                "notification": str(notification.name),
                "notification_log": str(notification_log),
            }
        if effect == "workflow_permission":
            role_name = _fixture_name("Workflow Role")
            user = f"phase8-workflow-{frappe.generate_hash(length=6)}@example.invalid"
            denied_user = f"phase8-workflow-denied-{frappe.generate_hash(length=6)}@example.invalid"
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "name": role_name,
                    "role_name": role_name,
                    "is_custom": 1,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)
            for email, roles in [(user, [role_name]), (denied_user, [])]:
                frappe.get_doc(
                    {
                        "doctype": "User",
                        "email": email,
                        "first_name": "Phase8 Workflow",
                        "enabled": 1,
                        "send_welcome_email": 0,
                        "roles": [{"role": role} for role in roles],
                    }
                ).insert(ignore_permissions=True)
            frappe.get_doc(
                {
                    "doctype": "Custom DocPerm",
                    "parent": "Quotation",
                    "parenttype": "DocType",
                    "parentfield": "permissions",
                    "role": role_name,
                    "permlevel": 0,
                    "read": 1,
                    "write": 1,
                    "create": 1,
                }
            ).insert(ignore_permissions=True)
            for dependency_doctype in [
                "Item",
                "Account",
                "Customer",
                "Price List",
                "UOM",
            ]:
                frappe.get_doc(
                    {
                        "doctype": "Custom DocPerm",
                        "parent": dependency_doctype,
                        "parenttype": "DocType",
                        "parentfield": "permissions",
                        "role": role_name,
                        "permlevel": 0,
                        "read": 1,
                    }
                ).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="Quotation")
            for dependency_doctype in [
                "Item",
                "Account",
                "Customer",
                "Price List",
                "UOM",
            ]:
                frappe.clear_cache(doctype=dependency_doctype)

            draft_state = _fixture_name("Workflow Draft")
            approved_state = _fixture_name("Workflow Approved")
            action_name = _fixture_name("Workflow Approve")
            for state in [draft_state, approved_state]:
                frappe.get_doc(
                    {
                        "doctype": "Workflow State",
                        "name": state,
                        "workflow_state_name": state,
                        "style": "Primary",
                    }
                ).insert(ignore_permissions=True)
            frappe.get_doc(
                {
                    "doctype": "Workflow Action Master",
                    "name": action_name,
                    "workflow_action_name": action_name,
                }
            ).insert(ignore_permissions=True)
            workflow = frappe.get_doc(
                {
                    "doctype": "Workflow",
                    "name": _fixture_name("Workflow Effect"),
                    "workflow_name": _fixture_name("Workflow Effect"),
                    "document_type": "Quotation",
                    "workflow_state_field": "workflow_state",
                    "is_active": 1,
                    "send_email_alert": 0,
                    "states": [
                        {
                            "state": draft_state,
                            "doc_status": "0",
                            "allow_edit": role_name,
                        },
                        {
                            "state": approved_state,
                            "doc_status": "0",
                            "allow_edit": role_name,
                        },
                    ],
                    "transitions": [
                        {
                            "state": draft_state,
                            "action": action_name,
                            "next_state": approved_state,
                            "allowed": role_name,
                            "allow_self_approval": 1,
                        }
                    ],
                }
            ).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="Workflow")
            quotation = _make_effect_quotation(prerequisites).insert(
                ignore_permissions=True
            )
            if quotation.workflow_state != draft_state:
                raise AssertionError("Workflow did not assign its initial state")

            previous_user = frappe.session.user or "Administrator"
            try:
                frappe.set_user(denied_user)
                denied = frappe.has_permission(
                    "Quotation", ptype="write", doc=quotation
                )
                frappe.set_user(user)
                allowed = frappe.has_permission(
                    "Quotation", ptype="write", doc=quotation
                )
                from frappe.model.workflow import apply_workflow

                quotation.flags.ignore_permissions = True
                transitioned = apply_workflow(quotation, action_name)
            finally:
                frappe.set_user(previous_user)
            if denied or not allowed:
                raise AssertionError("Custom DocPerm user matrix mismatch")
            if transitioned.workflow_state != approved_state:
                raise AssertionError("Workflow transition did not reach approved state")
            return {
                "ok": True,
                "effect": effect,
                "workflow": str(workflow.name),
                "denied_without_role": True,
                "allowed_with_role": True,
                "state": approved_state,
            }
        raise ValueError(f"unknown cross-cutting effect: {effect}")
    finally:
        frappe.db.rollback()
        frappe.clear_cache()
        frappe.in_test = previous_in_test
        cleanup_registry_residue()
