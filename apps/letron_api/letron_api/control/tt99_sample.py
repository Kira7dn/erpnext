"""Reusable rollback-safe TT99 sample data runner.

The sample is JSON because it is reviewable, diffable and can describe both
accounting events and accounting-owned B09 inputs.  This module resolves
account numbers to native ERPNext Accounts and submits native Journal Entries;
it never inserts GL Entry rows directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SAMPLE = Path("/etc/letron/config/fixtures/tt99/tt99-vnd-realistic.json")
SUPPORTED_SCHEMA_VERSION = 1


def _sample_path(sample_path: str | None) -> Path:
    if sample_path:
        candidate = Path(sample_path)
        if not candidate.is_absolute():
            candidate = Path(os.environ.get("LETRON_CONFIG_DIR", "/etc/letron/config")) / candidate
        return candidate
    return DEFAULT_SAMPLE


def load_sample(sample_path: str | None = None) -> dict[str, Any]:
    path = _sample_path(sample_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("TT99 sample root must be an object")
    validate_sample(payload)
    return payload


def validate_sample(sample: dict[str, Any]) -> None:
    if int(sample.get("schema_version", 0)) != SUPPORTED_SCHEMA_VERSION:
        raise ValueError("Unsupported TT99 sample schema_version")
    for key in ("sample_id", "company", "currency", "periods", "journal_entries", "b09_inputs"):
        if not sample.get(key):
            raise ValueError(f"TT99 sample requires {key}")
    if sample["currency"] != "VND":
        raise ValueError("TT99 sample currently supports VND only")
    periods = sample["periods"]
    if not isinstance(periods, dict) or not {"current", "comparative"}.issubset(periods):
        raise ValueError("TT99 sample requires current and comparative periods")
    period_ranges: dict[str, tuple[str, str]] = {}
    for name in ("current", "comparative"):
        value = periods[name]
        if not isinstance(value, dict) or not value.get("from_date") or not value.get("to_date"):
            raise ValueError(f"TT99 sample period {name} is invalid")
        period_ranges[name] = (str(value["from_date"]), str(value["to_date"]))
    entries = sample["journal_entries"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("TT99 sample journal_entries must be a non-empty list")
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("TT99 journal entry must be an object")
        entry_id = str(entry.get("id") or "")
        if not entry_id or entry_id in seen_ids:
            raise ValueError(f"TT99 journal entry id is missing or duplicated: {entry_id}")
        seen_ids.add(entry_id)
        period = str(entry.get("period") or "")
        posting_date = str(entry.get("posting_date") or "")
        if period not in period_ranges:
            raise ValueError(f"TT99 journal entry {entry_id} has an invalid period")
        start, end = period_ranges[period]
        if not start <= posting_date <= end:
            raise ValueError(f"TT99 journal entry {entry_id} is outside its period")
        lines = entry.get("lines")
        if not isinstance(lines, list) or len(lines) < 2:
            raise ValueError(f"TT99 journal entry {entry_id} needs at least two lines")
        debit = sum(float(line.get("debit") or 0) for line in lines if isinstance(line, dict))
        credit = sum(float(line.get("credit") or 0) for line in lines if isinstance(line, dict))
        if debit <= 0 or abs(debit - credit) > 0.0005:
            raise ValueError(f"TT99 journal entry {entry_id} is not balanced")
        for line in lines:
            if not isinstance(line, dict) or not line.get("account_code"):
                raise ValueError(f"TT99 journal entry {entry_id} has an invalid account line")
            if float(line.get("debit") or 0) < 0 or float(line.get("credit") or 0) < 0:
                raise ValueError(f"TT99 journal entry {entry_id} has a negative amount")
    if not isinstance(sample["b09_inputs"], dict):
        raise TypeError("TT99 b09_inputs must be an object")


def _account(frappe: Any, company: str, code: str) -> str:
    name = frappe.db.get_value(
        "Account",
        {"company": company, "account_number": ["like", f"{code}%"], "is_group": 0},
        "name",
    )
    if not name:
        raise RuntimeError(f"Missing native Account {code} for {company}")
    return str(name)


def _cost_center(frappe: Any, company: str) -> str:
    name = frappe.db.get_value(
        "Cost Center", {"company": company, "is_group": 0, "disabled": 0}, "name"
    )
    if not name:
        raise RuntimeError(f"Missing native Cost Center for {company}")
    return str(name)


def _create_journal_entry(frappe: Any, company: str, entry: dict[str, Any], cost_center: str, sample_id: str) -> str:
    remark = f"TT99-SAMPLE|sample={sample_id}|entry={entry['id']}|{entry['purpose']}"
    existing = frappe.db.get_value(
        "GL Entry", {"company": company, "remarks": remark, "is_cancelled": 0}, "voucher_no"
    )
    if existing:
        return str(existing)
    rows = []
    for line in entry["lines"]:
        debit = float(line.get("debit") or 0)
        credit = float(line.get("credit") or 0)
        account = _account(frappe, company, str(line["account_code"]))
        rows.append({
            "account": account,
            "cost_center": cost_center,
            "debit": debit,
            "credit": credit,
            "debit_in_account_currency": debit,
            "credit_in_account_currency": credit,
        })
    doc = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Journal Entry",
        "company": company,
        "posting_date": entry["posting_date"],
        "due_date": entry["posting_date"],
        "remark": remark,
        "user_remark": remark,
        "multi_currency": 0,
        "party_not_required": 1,
        "accounts": rows,
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    doc.submit()
    return str(doc.name)


def _report_line(report: dict[str, Any], code: str) -> dict[str, Any]:
    return next((line for line in report.get("lines", []) if str(line.get("code")) == code), {})


def _b09_package(frappe: Any, sample: dict[str, Any], issue: bool) -> dict[str, Any]:
    from letron_api.finance import vas_reports

    company = str(sample["company"])
    period = sample["periods"]["current"]
    sample_id = str(sample["sample_id"])
    existing = frappe.get_all(
        "Letron VAS Report Package",
        filters={"company": company, "form_code": "B09-DN", "from_date": period["from_date"], "to_date": period["to_date"]},
        fields=["name", "status", "consolidation_scope"],
        order_by="modified desc",
        limit_page_length=0,
    )
    package = next(
        (row for row in existing if sample_id in str(row.get("consolidation_scope") or "")),
        None,
    )
    if package:
        doc = frappe.get_doc("Letron VAS Report Package", package["name"])
    else:
        doc = frappe.get_doc(
            vas_reports.create_b09_package(
                company,
                period["from_date"],
                period["to_date"],
                accounting_inputs=sample["b09_inputs"],
            )
        )
        doc.consolidation_scope = json.dumps({"sample_id": sample_id, "mode": "sample"}, ensure_ascii=False)
        doc.save(ignore_permissions=True)
    if doc.status == "Draft":
        doc.status = "Review"
        doc.save(ignore_permissions=True)
    if doc.status == "Review":
        doc.status = "Closed"
        doc.save(ignore_permissions=True)
    if issue and doc.status == "Closed" and doc.docstatus == 0:
        doc.status = "Issued"
        doc.flags.ignore_permissions = True
        doc.submit()
    doc.reload()
    return {"name": str(doc.name), "status": str(doc.status), "docstatus": int(doc.docstatus)}


def apply(sample_path: str | None = None, commit: bool = False, issue_b09: bool = False) -> dict[str, Any]:
    """Apply the sample and return report evidence; rollback unless commit=True."""

    import frappe

    from letron_api.finance import vas_reports

    sample_path = sample_path or os.environ.get("LETRON_TT99_SAMPLE_PATH")
    commit = commit or os.environ.get("LETRON_TT99_SAMPLE_COMMIT") == "1"
    issue_b09 = issue_b09 or os.environ.get("LETRON_TT99_SAMPLE_ISSUE_B09") == "1"
    sample = load_sample(sample_path)
    company = str(sample["company"])
    current = sample["periods"]["current"]
    comparative = sample["periods"]["comparative"]
    if not frappe.db.exists("Company", company):
        raise RuntimeError(f"Unknown sample Company: {company}")
    cost_center = _cost_center(frappe, company)
    journal_entries: list[str] = []
    current_journal_entries: list[str] = []
    for entry in sample["journal_entries"]:
        journal_entry = _create_journal_entry(
            frappe, company, entry, cost_center, str(sample["sample_id"])
        )
        journal_entries.append(journal_entry)
        if entry["period"] == "current":
            current_journal_entries.append(journal_entry)
    current_report = vas_reports.statutory_cash_flow(
        company, current["from_date"], current["to_date"],
        comparative_from_date=comparative["from_date"],
        comparative_to_date=comparative["to_date"],
    )
    if not current_report["ok"]:
        raise AssertionError({"b03_current": current_report})
    current_line_50 = float(_report_line(current_report, "50").get("amount") or 0)
    current_line_60 = float(_report_line(current_report, "60").get("amount") or 0)
    current_line_61 = float(_report_line(current_report, "61").get("amount") or 0)
    current_line_70 = float(_report_line(current_report, "70").get("amount") or 0)
    native_metrics = current_report["native_metrics"]
    account_rows = frappe.get_all(
        "Account", filters={"company": company, "is_group": 0},
        fields=["name", "account_number"], limit_page_length=0,
    )
    account_numbers = {str(row["name"]): str(row.get("account_number") or "") for row in account_rows}
    cash_names = {name for name, code in account_numbers.items() if code.startswith(("111", "112", "113"))}
    cash_rows = frappe.get_all(
        "GL Entry", filters={"company": company, "voucher_no": ["in", current_journal_entries], "is_cancelled": 0},
        fields=["account", "debit", "credit"], limit_page_length=0,
    )
    sample_cash_delta = sum(
        float(row.get("debit") or 0) - float(row.get("credit") or 0)
        for row in cash_rows if str(row.get("account")) in cash_names
    )
    expected_closing = current_line_50 + current_line_60 + current_line_61
    if abs(current_line_50 - sample_cash_delta) > 0.0005 or abs(float(native_metrics["closing_cash"]) - (float(native_metrics["opening_cash"]) + sample_cash_delta)) > 0.0005:
        raise AssertionError({"cash_reconciliation": {
            "sample_cash_delta": sample_cash_delta,
            "report_line_50": current_line_50,
            "expected_closing": expected_closing,
            "line_70": current_line_70,
            "native_closing_cash": native_metrics["closing_cash"],
            "metrics": current_report["native_metrics"],
            "events": current_report["cash_flow_events"],
            "lines": current_report["lines"],
        }})
    b09 = _b09_package(frappe, sample, issue_b09)
    result = {
        "ok": True,
        "sample_id": sample["sample_id"],
        "company": company,
        "currency": sample["currency"],
        "mode": "commit" if commit else "rollback",
        "journal_entries": journal_entries,
        "b03": {
            "ok": bool(current_report["ok"]),
            "cash_flow_exceptions": current_report["cash_flow_exceptions"],
            "unresolved_line_codes": current_report["unresolved_line_codes"],
            "line_50": current_line_50,
            "line_60": current_line_60,
            "line_61": current_line_61,
            "line_70": current_line_70,
            "native_closing_cash": float(native_metrics["closing_cash"]),
        },
        "b09": b09,
    }
    if commit:
        frappe.db.commit()
    else:
        frappe.db.rollback()
    frappe.clear_cache()
    return result
