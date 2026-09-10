"""Typed banking adapters for the Next.js Accounting frontend."""

from __future__ import annotations

import json
from typing import Any

import frappe


REPORTS = {
    "bank-reconciliation-statement": "Bank Reconciliation Statement",
    "bank-clearance-summary": "Bank Clearance Summary",
    "incorrectly-cleared": "Cheques and Deposits Incorrectly cleared",
}

RECONCILIATION_ACTIONS = {
    "reconcile-vouchers": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.reconcile_vouchers",
    "unreconcile-transaction": "erpnext.accounts.doctype.bank_transaction.bank_transaction.unreconcile_transaction",
    "create-payment-entry": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_payment_entry_and_reconcile",
    "create-bulk-payment-entry": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_bulk_payment_entry_and_reconcile",
    "create-internal-transfer": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_internal_transfer",
    "create-bulk-internal-transfer": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_bulk_internal_transfer",
    "create-bank-entry": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_bank_entry_and_reconcile",
    "create-bulk-bank-entry": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_bulk_bank_entry_and_reconcile",
    "get-older-transactions": "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.get_older_unreconciled_transactions",
    "set-closing-balance": "erpnext.accounts.doctype.bank_account.bank_account.set_closing_balance_as_per_statement",
}


def _json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except (TypeError, ValueError):
            return value
    return value


def _arg(name: str, default: Any = None) -> Any:
    return _json(frappe.form_dict.get(name), default)


def _details(statement_import_id: str) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import get_statement_details

    return get_statement_details(statement_import_id)


@frappe.whitelist(methods=["GET"])
def statement_imports(limit_page_length: int = 50, start: int = 0) -> list[dict[str, Any]]:
    frappe.has_permission("Bank Statement Import Log", "read", throw=True)
    return frappe.get_all("Bank Statement Import Log", fields="*", order_by="modified desc", limit_page_length=min(int(limit_page_length), 200), limit_start=int(start))


@frappe.whitelist(methods=["POST"])
def statement_import_create(bank_account: str, file: str, **kwargs: Any) -> dict[str, Any]:
    if not isinstance(file, str) or not file:
        frappe.throw("file must be an existing File URL", exc=frappe.ValidationError)
    document = frappe.get_doc({"doctype": "Bank Statement Import Log", "bank_account": bank_account, "file": file})
    document.insert()
    return document.as_dict()


@frappe.whitelist(methods=["POST"])
def statement_import_upload() -> dict[str, Any]:
    uploaded = frappe.request.files.get("file")
    if not uploaded:
        frappe.throw("file is required", exc=frappe.ValidationError)
    from frappe.utils.file_manager import save_file

    document = save_file(uploaded.filename, uploaded.read(), None, None, is_private=1)
    return {"file_url": document.file_url, "file_name": document.file_name}


@frappe.whitelist(methods=["GET"])
def statement_import_get(statement_import_id: str) -> dict[str, Any]:
    document = frappe.get_doc("Bank Statement Import Log", statement_import_id)
    document.check_permission("read")
    return document.as_dict()


@frappe.whitelist(methods=["PUT"])
def statement_import_update(statement_import_id: str, **kwargs: Any) -> dict[str, Any]:
    document = frappe.get_doc("Bank Statement Import Log", statement_import_id)
    document.check_permission("write")
    payload = _json(frappe.request.get_data(as_text=True), {}) or {}
    if not isinstance(payload, dict):
        frappe.throw("Request body must be an object", exc=frappe.ValidationError)
    protected = {"doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus"}
    for field, value in payload.items():
        if field not in protected and hasattr(document, field):
            document.set(field, value)
    document.save()
    return document.as_dict()


@frappe.whitelist(methods=["GET"])
def reconciliation_transactions(bank_account: str, from_date: str | None = None, to_date: str | None = None, all_transactions: Any = False) -> list[dict[str, Any]]:
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_bank_transactions

    frappe.has_permission("Bank Account", "read", bank_account, throw=True)
    return get_bank_transactions(bank_account, from_date, to_date, bool(_json(all_transactions, False)))


@frappe.whitelist(methods=["GET"])
def reconciliation_balance(bank_account: str, till_date: str, company: str) -> Any:
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_account_balance

    return get_account_balance(bank_account, till_date, company)


@frappe.whitelist(methods=["GET"])
def reconciliation_linked_payments(bank_transaction_name: str, document_types: Any = None, from_date: str | None = None, to_date: str | None = None, filter_by_reference_date: Any = False, from_reference_date: str | None = None, to_reference_date: str | None = None) -> list[dict[str, Any]]:
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_linked_payments

    frappe.get_doc("Bank Transaction", bank_transaction_name).check_permission("read")
    return get_linked_payments(bank_transaction_name, _json(document_types), from_date, to_date, _json(filter_by_reference_date, False), from_reference_date, to_reference_date)


@frappe.whitelist(methods=["POST"])
def reconciliation_update_clearance(payment_document: str, payment_entry: str, account: str, clearance_date: str | None = None) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import update_clearance_date

    update_clearance_date(payment_document, payment_entry, account, clearance_date)
    return {"payment_document": payment_document, "payment_entry": payment_entry, "clearance_date": clearance_date}


@frappe.whitelist(methods=["POST"])
def reconciliation_clear_clearance(voucher_type: str, voucher_name: str) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import clear_clearing_date

    clear_clearing_date(voucher_type, voucher_name)
    return {"voucher_type": voucher_type, "voucher_name": voucher_name, "clearance_date": None}


@frappe.whitelist(methods=["POST"])
def reconciliation_action(action: str, payload: Any = None) -> Any:
    method_path = RECONCILIATION_ACTIONS.get(action)
    if not method_path:
        frappe.throw("Unsupported reconciliation action", exc=frappe.ValidationError)
    arguments = _json(payload, {})
    if not isinstance(arguments, dict):
        frappe.throw("payload must be an object", exc=frappe.ValidationError)
    return frappe.get_attr(str(method_path))(**arguments)


@frappe.whitelist(methods=["POST"])
def run_rule_evaluation(force_evaluate: Any = False) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_transaction_rule.bank_transaction_rule import run_rule_evaluation as native_run

    return native_run(bool(_json(force_evaluate, False))) or {"ok": True}


@frappe.whitelist(methods=["GET"])
def report(report_key: str, filters: Any = None) -> dict[str, Any]:
    report_name = REPORTS.get(report_key)
    if not report_name:
        frappe.throw("Unsupported banking report", exc=frappe.ValidationError)
    from frappe.desk.query_report import run

    return run(report_name=report_name, filters=_json(filters, {}), ignore_prepared_report=True)


@frappe.whitelist(methods=["GET"])
def statement_details(statement_import_id: str) -> dict[str, Any]:
    return _details(statement_import_id)


@frappe.whitelist(methods=["POST"])
def statement_update_pdf_tables(statement_import_id: str, tables: Any) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import update_pdf_tables

    return update_pdf_tables(statement_import_id, _json(tables, []))


@frappe.whitelist(methods=["POST"])
def statement_reextract_pdf_table(statement_import_id: str, page: int, table_index: int, bbox: Any) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import reextract_pdf_table

    return reextract_pdf_table(statement_import_id, int(page), int(table_index), _json(bbox, []))


@frappe.whitelist(methods=["POST"])
def statement_set_pdf_table_header(statement_import_id: str, page: int, table_index: int, header_index: int) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import set_pdf_table_header

    return set_pdf_table_header(statement_import_id, int(page), int(table_index), int(header_index))


@frappe.whitelist(methods=["POST"])
def statement_update_column_mapping(statement_import_id: str, column_mapping: Any) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import update_column_mapping

    return update_column_mapping(statement_import_id, _json(column_mapping, []))


@frappe.whitelist(methods=["POST"])
def statement_set_header_index(statement_import_id: str, header_index: int) -> dict[str, Any]:
    from erpnext.accounts.doctype.bank_statement_import_log.bank_statement_import_log import set_header_index

    return set_header_index(statement_import_id, int(header_index))


@frappe.whitelist(methods=["GET"])
def accounts_settings() -> dict[str, Any]:
    document = frappe.get_doc("Accounts Settings", "Accounts Settings")
    document.check_permission("read")
    return document.as_dict()


@frappe.whitelist(methods=["PUT"])
def accounts_settings_update(**kwargs: Any) -> dict[str, Any]:
    document = frappe.get_doc("Accounts Settings", "Accounts Settings")
    document.check_permission("write")
    payload = _json(frappe.request.get_data(as_text=True), {}) or {}
    if not isinstance(payload, dict):
        frappe.throw("Request body must be an object", exc=frappe.ValidationError)
    protected = {"doctype", "name", "owner", "creation", "modified", "modified_by", "docstatus"}
    for field, value in payload.items():
        if field not in protected and hasattr(document, field):
            document.set(field, value)
    document.save()
    return document.as_dict()
