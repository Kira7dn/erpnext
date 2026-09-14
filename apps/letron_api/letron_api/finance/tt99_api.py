"""Public TT99 package and guarded accounting setup APIs.

The module deliberately keeps the public surface narrow.  Report values are
snapshots of native ERPNext financial reports and documents are always written
through Frappe controllers; this module never inserts GL Entry rows.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import frappe

from letron_api.control.policy import load_policy

FORM_CODES = frozenset({"B01-DN", "B02-DN", "B03-DN", "B09-DN"})
PACKAGE_DOCTYPE = "Letron VAS Report Package"
PACKAGE_STATUSES = frozenset({"Draft", "Review", "Closed", "Issued", "Rejected"})
READ_ONLY_MASTER_FIELDS = {
    "Company": "*",
    "Account": "*",
    "Finance Book": "*",
    "Fiscal Year": "*",
    "Cost Center": "*",
}


def _payload() -> dict[str, Any]:
    raw = frappe.request.get_data(as_text=True)
    if not raw:
        return {}
    value = frappe.parse_json(raw)
    if not isinstance(value, dict):
        frappe.throw("Request body must be an object", exc=frappe.ValidationError)
    return value


def _query(name: str, default: Any = None) -> Any:
    value = frappe.request.args.get(name)
    return default if value in (None, "") else value


def _limit() -> tuple[int, int]:
    try:
        limit = min(max(int(_query("limit_page_length", 50)), 1), 200)
        start = max(int(_query("limit_start", 0)), 0)
    except (TypeError, ValueError):
        frappe.throw("Pagination values are invalid", exc=frappe.ValidationError)
    return limit, start


def _json_value(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _permission(doctype: str, ptype: str, document: Any | None = None) -> None:
    if document is not None:
        document.check_permission(ptype)
    else:
        frappe.has_permission(doctype, ptype, throw=True)


def _company(company: str) -> str:
    if not company or not frappe.db.exists("Company", company):
        frappe.throw(f"Unknown Company: {company}", exc=frappe.DoesNotExistError)
    document = frappe.get_doc("Company", company)
    _permission("Company", "read", document)
    return company


def _company_of(document: Any, company: str | None = None) -> None:
    actual = str(getattr(document, "company", "") or "")
    if company and actual != company:
        frappe.throw("Document is outside the requested Company scope", exc=frappe.PermissionError)
    if actual:
        _company(actual)


def _audit(document: Any, action: str, changes: dict[str, Any] | None = None) -> None:
    """Write an actor/timestamp audit comment without creating a new DocType."""

    comment = getattr(document, "add_comment", None)
    if callable(comment):
        actor = getattr(frappe.local, "letron_gateway_actor", None)
        authorization = getattr(frappe.local, "letron_request_identity", None)
        payload = {
            "action": action,
            "actor": actor or frappe.session.user,
            "authorization": authorization,
            "changes": changes or {},
        }
        comment("Info", json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _list(doctype: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    _permission(doctype, "read")
    limit, start = _limit()
    filters = filters or {}
    items = frappe.get_list(
        doctype,
        filters=filters,
        fields="*",
        order_by="modified desc",
        limit_page_length=limit,
        limit_start=start,
    )
    total = frappe.db.count(doctype, filters=filters)
    return {"items": [dict(item) for item in items], "total": int(total)}


def _master(doctype: str, name: str) -> dict[str, Any]:
    document = frappe.get_doc(doctype, name)
    _permission(doctype, "read", document)
    return document.as_dict()


def _policy_hash(policy: dict[str, Any]) -> str:
    canonical = json.dumps(policy, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _package_doc(name: str) -> Any:
    document = frappe.get_doc(PACKAGE_DOCTYPE, name)
    _permission(PACKAGE_DOCTYPE, "read", document)
    return document


def _package_response(document: Any) -> dict[str, Any]:
    result = document.as_dict()
    for field, target in (("validation_json", "validation"), ("lines_json", "lines")):
        raw = result.pop(field, None)
        result[target] = _json_value(raw, {} if target == "validation" else [])
    result["sources"] = [dict(row) for row in result.get("sources") or []]
    result["notes"] = [dict(row) for row in result.get("notes") or []]
    return result


def _validate_range(company: str, from_date: str, to_date: str) -> None:
    if not from_date or not to_date or from_date > to_date:
        frappe.throw("from_date and to_date must be an ordered range", exc=frappe.ValidationError)
    from letron_api.finance.vas_reports import _fiscal_year_for_range

    _fiscal_year_for_range(company, from_date, to_date)


def _closing_status(company: str, to_date: str) -> dict[str, Any]:
    closed = bool(
        frappe.db.exists(
            "Period Closing Voucher",
            {"company": company, "docstatus": 1, "period_end_date": [">=", to_date]},
        )
    )
    return {"required": bool(load_policy().get("shared", {}).get("consolidation", {}).get("require_closed_period", False)), "closed": closed, "through": to_date}


def _report_snapshot(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    company = _company(str(payload.get("company") or ""))
    form_code = str(payload.get("form_code") or "")
    if form_code not in FORM_CODES:
        frappe.throw("form_code must be B01-DN, B02-DN, B03-DN or B09-DN", exc=frappe.ValidationError)
    from_date = str(payload.get("from_date") or "")
    to_date = str(payload.get("to_date") or "")
    _validate_range(company, from_date, to_date)
    comparative_from = payload.get("comparative_from_date")
    comparative_to = payload.get("comparative_to_date")
    if (comparative_from is None) != (comparative_to is None):
        frappe.throw("Comparative dates must be provided together", exc=frappe.ValidationError)
    if comparative_from and comparative_to:
        _validate_range(company, str(comparative_from), str(comparative_to))
    finance_book = payload.get("finance_book") or None
    from letron_api.finance import vas_reports

    if form_code == "B09-DN":
        snapshot = vas_reports.b09_report(company, from_date, to_date, finance_book, comparative_from, comparative_to)
        rows = list(snapshot.get("notes") or [])
    elif form_code == "B03-DN":
        snapshot = vas_reports.statutory_cash_flow(company, from_date, to_date, finance_book, comparative_from, comparative_to)
        rows = list(snapshot.get("lines") or [])
    else:
        snapshot = vas_reports.statutory_report(form_code, company, from_date, to_date, finance_book, comparative_from, comparative_to)
        rows = list(snapshot.get("lines") or [])

    accounting_inputs = payload.get("accounting_inputs") or {}
    if form_code == "B09-DN" and isinstance(accounting_inputs, dict):
        for row in rows:
            supplied = accounting_inputs.get(str(row.get("code")))
            if supplied is None:
                continue
            if isinstance(supplied, dict) and "data" in supplied:
                row["data"] = supplied.get("data")
                row["source_refs"] = [str(value) for value in supplied.get("source_refs") or []]
            else:
                row["data"] = supplied
            row["status"] = "derived"
    unresolved = [str(row.get("code")) for row in rows if str(row.get("status")) not in {"derived", "not_applicable"}]
    unresolved.extend(str(value) for value in snapshot.get("unresolved_line_codes") or [])
    statement_ok = all(value.get("ok") is True for value in snapshot.get("statement_data", {}).values()) if form_code == "B09-DN" else snapshot.get("ok") is True
    validation = {
        "ok": not unresolved and statement_ok and not snapshot.get("unmapped_account_codes") and not snapshot.get("cash_flow_exceptions"),
        "statement_ok": statement_ok,
        "unresolved": sorted(set(unresolved)),
        "unmapped_account_codes": list(snapshot.get("unmapped_account_codes") or []),
        "cash_flow_exceptions": list(snapshot.get("cash_flow_exceptions") or []),
        "closing": _closing_status(company, to_date),
    }
    policy = load_policy()
    metadata = {
        "policy": policy,
        "policy_version": int(policy.get("version", 0)),
        "policy_hash": _policy_hash(policy),
        "source_cutoff": frappe.utils.now_datetime(),
        "accounting_currency": snapshot.get("currency") or frappe.get_cached_value("Company", company, "default_currency"),
        "reporting_currency": policy.get("shared", {}).get("coa_template", {}).get("reporting", {}).get("reporting_currency") or policy.get("shared", {}).get("consolidation", {}).get("reporting_currency"),
    }
    return snapshot, rows, {"validation": validation, **metadata}


def _apply_snapshot(document: Any, payload: dict[str, Any]) -> Any:
    snapshot, rows, metadata = _report_snapshot({**document.as_dict(), **payload})
    document.accounting_currency = metadata["accounting_currency"]
    document.reporting_currency = metadata["reporting_currency"]
    document.policy_version = metadata["policy_version"]
    document.policy_hash = metadata["policy_hash"]
    document.source_cutoff = metadata["source_cutoff"]
    document.validation_json = json.dumps(metadata["validation"], ensure_ascii=False, sort_keys=True, default=str)
    document.lines_json = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    document.notes = []
    document.sources = [{
        "source_type": str(snapshot.get("native_source") or "native_erpnext_report"),
        "source_name": str(snapshot.get("statement") or snapshot.get("form_code") or document.form_code),
        "detail_json": json.dumps({"company": document.company, "from_date": document.from_date, "to_date": document.to_date}, ensure_ascii=False, sort_keys=True),
    }]
    if document.form_code == "B09-DN":
        for row in rows:
            document.append("notes", {
                "code": row.get("code"),
                "title": row.get("name") or row.get("title") or row.get("code"),
                "source": row.get("source") or "native_erpnext_report",
                "data_json": json.dumps(row.get("data"), ensure_ascii=False, sort_keys=True, default=str),
                "status": row.get("status") or "incomplete",
                "source_refs": json.dumps(row.get("source_refs") or [], ensure_ascii=False),
            })
    return document


@frappe.whitelist()
def list_report_packages() -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for field in ("company", "form_code", "status", "from_date", "to_date"):
        value = _query(field)
        if value:
            filters[field] = value
    return _list(PACKAGE_DOCTYPE, filters)


@frappe.whitelist()
def get_report_package(name: str) -> dict[str, Any]:
    return _package_response(_package_doc(name))


@frappe.whitelist()
def create_report_package() -> dict[str, Any]:
    payload = _payload()
    required = ("company", "form_code", "from_date", "to_date")
    if any(not payload.get(key) for key in required):
        frappe.throw("company, form_code, from_date and to_date are required", exc=frappe.ValidationError)
    _permission(PACKAGE_DOCTYPE, "create")
    document = frappe.get_doc({"doctype": PACKAGE_DOCTYPE, **{key: payload[key] for key in ("company", "form_code", "from_date", "to_date", "comparative_from_date", "comparative_to_date", "finance_book", "consolidation_scope") if key in payload}, "status": "Draft"})
    _apply_snapshot(document, payload)
    document.insert()
    _audit(document, "create", {"form_code": getattr(document, "form_code", None)})
    return _package_response(document)


@frappe.whitelist()
def update_report_package(name: str) -> dict[str, Any]:
    document = _package_doc(name)
    if str(document.status) not in {"Draft", "Rejected"} or int(document.docstatus or 0):
        frappe.throw("Only Draft or Rejected report packages can be edited", exc=frappe.PermissionError)
    _permission(PACKAGE_DOCTYPE, "write", document)
    payload = _payload()
    allowed = {"company", "form_code", "from_date", "to_date", "comparative_from_date", "comparative_to_date", "finance_book", "consolidation_scope", "accounting_inputs"}
    before = {key: getattr(document, key, None) for key in allowed if hasattr(document, key)}
    for key in allowed - {"accounting_inputs"}:
        if key in payload:
            setattr(document, key, payload[key])
    _apply_snapshot(document, payload)
    document.save()
    _audit(document, "update", {key: getattr(document, key, None) for key in before if before[key] != getattr(document, key, None)})
    return _package_response(document)


def _transition(name: str, expected: str, target: str, action: str, reason: str | None = None) -> dict[str, Any]:
    document = _package_doc(name)
    if str(document.status) != expected or int(document.docstatus or 0):
        frappe.throw(f"Report package must be {expected} before {action}", exc=frappe.ValidationError)
    _permission(PACKAGE_DOCTYPE, "write", document)
    if target == "Closed":
        validation = _json_value(document.validation_json, {})
        if not validation.get("ok"):
            frappe.throw("Only a valid report package can be closed", exc=frappe.ValidationError)
        closing = validation.get("closing") or _closing_status(str(document.company), str(document.to_date))
        if closing.get("required") and not closing.get("closed"):
            frappe.throw("Report period must have a submitted Period Closing Voucher", exc=frappe.ValidationError)
    document.status = target
    if target == "Review":
        document.reviewed_by = frappe.session.user
        document.reviewed_at = frappe.utils.now_datetime()
    elif target == "Closed":
        document.closed_by = frappe.session.user
        document.closed_at = frappe.utils.now_datetime()
    elif target == "Rejected":
        rejection_reason = reason or ""
        if not rejection_reason.strip():
            frappe.throw("reason is required when rejecting a report package", exc=frappe.ValidationError)
        document.rejection_reason = rejection_reason.strip()
        document.rejected_by = frappe.session.user
        document.rejected_at = frappe.utils.now_datetime()
    document.save()
    _audit(document, action, {"reason": reason} if reason else None)
    return _package_response(document)


@frappe.whitelist()
def review_report_package(name: str) -> dict[str, Any]:
    return _transition(name, "Draft", "Review", "review")


@frappe.whitelist()
def close_report_package(name: str) -> dict[str, Any]:
    return _transition(name, "Review", "Closed", "close")


@frappe.whitelist()
def issue_report_package(name: str) -> dict[str, Any]:
    document = _package_doc(name)
    if str(document.status) != "Closed" or int(document.docstatus or 0):
        frappe.throw("Only a Closed report package can be issued", exc=frappe.ValidationError)
    _permission(PACKAGE_DOCTYPE, "submit", document)
    document.status = "Issued"
    document.issued_by = frappe.session.user
    document.issued_at = frappe.utils.now_datetime()
    document.submit()
    _audit(document, "issue")
    return _package_response(document)


@frappe.whitelist()
def reject_report_package(name: str) -> dict[str, Any]:
    payload = _payload()
    return _transition(name, "Review", "Rejected", "reject", str(payload.get("reason") or ""))


def _master_list(doctype: str, company: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if company:
        _company(company)
    filters = dict(extra or {})
    fieldnames = getattr(frappe.get_meta(doctype), "get_fieldnames", list)()
    if company and "company" in fieldnames:
        filters["company"] = company
    return _list(doctype, filters)


@frappe.whitelist()
def list_companies() -> dict[str, Any]:
    return _master_list("Company")


@frappe.whitelist()
def get_company(name: str) -> dict[str, Any]:
    return _master("Company", name)


@frappe.whitelist()
def list_accounts() -> dict[str, Any]:
    return _master_list("Account", str(_query("company") or "") or None)


@frappe.whitelist()
def get_account(name: str) -> dict[str, Any]:
    result = _master("Account", name)
    _company_of(frappe.get_doc("Account", name))
    return result


@frappe.whitelist()
def list_finance_books() -> dict[str, Any]:
    return _master_list("Finance Book")


@frappe.whitelist()
def get_finance_book(name: str) -> dict[str, Any]:
    return _master("Finance Book", name)


@frappe.whitelist()
def list_fiscal_years() -> dict[str, Any]:
    company = str(_query("company") or "") or None
    if not company:
        return _master_list("Fiscal Year")
    _company(company)
    parents = frappe.get_all("Fiscal Year Company", filters={"company": company}, fields=["parent"], limit_page_length=0)
    return _master_list("Fiscal Year", extra={"name": ["in", [row["parent"] for row in parents]]})


@frappe.whitelist()
def get_fiscal_year(name: str) -> dict[str, Any]:
    return _master("Fiscal Year", name)


@frappe.whitelist()
def list_cost_centers() -> dict[str, Any]:
    return _master_list("Cost Center", str(_query("company") or "") or None)


@frappe.whitelist()
def get_cost_center(name: str) -> dict[str, Any]:
    result = _master("Cost Center", name)
    _company_of(frappe.get_doc("Cost Center", name))
    return result


def _write_shareholder(payload: dict[str, Any], document: Any | None = None) -> Any:
    company = _company(str(payload.get("company") or getattr(document, "company", "") or ""))
    action = "update" if document is not None else "create"
    if document is None:
        _permission("Shareholder", "create")
        document = frappe.get_doc({"doctype": "Shareholder"})
    else:
        _permission("Shareholder", "write", document)
        if int(document.docstatus or 0):
            frappe.throw("Submitted or cancelled Shareholders cannot be edited", exc=frappe.PermissionError)
        _company_of(document, company)
    for field in ("title", "company", "naming_series"):
        if field in payload:
            setattr(document, field, payload[field])
    if not getattr(document, "title", None):
        frappe.throw("title is required", exc=frappe.ValidationError)
    if document.is_new():
        document.insert()
    else:
        document.save()
    _audit(document, action)
    return document.as_dict()


@frappe.whitelist()
def list_shareholders() -> dict[str, Any]:
    return _master_list("Shareholder", str(_query("company") or "") or None)


@frappe.whitelist()
def get_shareholder(name: str) -> dict[str, Any]:
    document = frappe.get_doc("Shareholder", name)
    _permission("Shareholder", "read", document)
    return document.as_dict()


@frappe.whitelist()
def create_shareholder() -> dict[str, Any]:
    return _write_shareholder(_payload())


@frappe.whitelist()
def update_shareholder(name: str) -> dict[str, Any]:
    document = frappe.get_doc("Shareholder", name)
    _permission("Shareholder", "read", document)
    return _write_shareholder(_payload(), document)


def _validate_pcv_payload(payload: dict[str, Any], document: Any | None = None) -> None:
    company = _company(str(payload.get("company") or getattr(document, "company", "") or ""))
    fiscal_year = str(payload.get("fiscal_year") or getattr(document, "fiscal_year", "") or "")
    if not fiscal_year or not frappe.db.exists("Fiscal Year", fiscal_year):
        frappe.throw("Unknown Fiscal Year", exc=frappe.DoesNotExistError)
    fiscal = frappe.get_doc("Fiscal Year", fiscal_year)
    _permission("Fiscal Year", "read", fiscal)
    if not any(str(row.company) == company for row in fiscal.get("companies") or []):
        frappe.throw("Fiscal Year is not assigned to the Company", exc=frappe.ValidationError)
    start = str(payload.get("period_start_date") or getattr(document, "period_start_date", "") or "")
    end = str(payload.get("period_end_date") or getattr(document, "period_end_date", "") or "")
    if not start or not end or start > end:
        frappe.throw("Period dates must be an ordered range", exc=frappe.ValidationError)
    if start < str(getattr(fiscal, "year_start_date", "")) or end > str(getattr(fiscal, "year_end_date", "")):
        frappe.throw("Closing period is outside the Fiscal Year", exc=frappe.ValidationError)
    today = frappe.utils.getdate() or date.fromisoformat(str(frappe.utils.nowdate()))
    if date.fromisoformat(end) > today:
        frappe.throw("A future period cannot be closed", exc=frappe.ValidationError)


@frappe.whitelist()
def list_period_closing_vouchers() -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for field in ("company", "fiscal_year"):
        value = _query(field)
        if value:
            filters[field] = value
    return _list("Period Closing Voucher", filters)


@frappe.whitelist()
def get_period_closing_voucher(name: str) -> dict[str, Any]:
    return _master("Period Closing Voucher", name)


@frappe.whitelist()
def create_period_closing_voucher() -> dict[str, Any]:
    payload = _payload()
    _validate_pcv_payload(payload)
    _permission("Period Closing Voucher", "create")
    fields = ("transaction_date", "company", "fiscal_year", "period_start_date", "period_end_date", "closing_account_head", "remarks")
    document = frappe.get_doc({"doctype": "Period Closing Voucher", **{key: payload[key] for key in fields if key in payload}})
    document.insert()
    _audit(document, "create")
    return document.as_dict()


@frappe.whitelist()
def update_period_closing_voucher(name: str) -> dict[str, Any]:
    document = frappe.get_doc("Period Closing Voucher", name)
    _permission("Period Closing Voucher", "write", document)
    if int(document.docstatus or 0):
        frappe.throw("A submitted Period Closing Voucher cannot be edited", exc=frappe.PermissionError)
    payload = _payload()
    _validate_pcv_payload({**document.as_dict(), **payload}, document)
    fields = ("transaction_date", "company", "fiscal_year", "period_start_date", "period_end_date", "closing_account_head", "remarks")
    for field in fields:
        if field in payload:
            setattr(document, field, payload[field])
    document.save()
    _audit(document, "update")
    return document.as_dict()


@frappe.whitelist()
def submit_period_closing_voucher(name: str) -> dict[str, Any]:
    document = frappe.get_doc("Period Closing Voucher", name)
    _permission("Period Closing Voucher", "submit", document)
    if int(document.docstatus or 0):
        frappe.throw("Period Closing Voucher is already submitted", exc=frappe.ValidationError)
    _validate_pcv_payload(document.as_dict(), document)
    document.submit()
    _audit(document, "submit")
    return document.as_dict()


@frappe.whitelist()
def cancel_period_closing_voucher(name: str) -> dict[str, Any]:
    document = frappe.get_doc("Period Closing Voucher", name)
    _permission("Period Closing Voucher", "cancel", document)
    if int(document.docstatus or 0) != 1:
        frappe.throw("Only a submitted Period Closing Voucher can be cancelled", exc=frappe.ValidationError)
    document.cancel()
    _audit(document, "cancel")
    return document.as_dict()
