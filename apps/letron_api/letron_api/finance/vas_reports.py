"""VAS statement views backed by ERPNext's native financial statement engine."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any


def _frappe() -> Any:
    import frappe

    return frappe


def _mapping(statement: str) -> list[dict[str, Any]]:
    from letron_api.control.policy import load_policy

    mapping = load_policy()["shared"]["coa_template"].get("bctc_mapping", {})
    lines = mapping.get("statements", {}).get(statement)
    if not isinstance(lines, list) or not lines:
        raise ValueError(f"Unsupported or empty VAS statement: {statement}")
    return lines


def _reporting_policy() -> dict[str, Any]:
    from letron_api.control.policy import load_policy

    return dict(load_policy()["shared"]["coa_template"].get("reporting", {}))


def _cash_flow_policy() -> dict[str, Any]:
    """Return the validated VAS 24 cash-flow policy contract."""
    reporting = _reporting_policy()
    cash_flow = reporting.get("cash_flow", {})
    if not isinstance(cash_flow, dict):
        raise TypeError("shared.coa_template.reporting.cash_flow must be a mapping")
    return cash_flow


def _native_metric_activity(
    company: str,
    from_date: str,
    to_date: str,
    metric: str,
    finance_book: str | None = None,
) -> float | None:
    """Derive a policy-mapped VAS 24 metric from native GL activity.

    The policy names the Account codes allowed to source each otherwise
    subledger-specific line.  An absent mapping returns ``None`` so a real
    report remains fail-closed instead of guessing a zero.
    """
    source_codes = _cash_flow_policy().get("metric_sources", {}).get(metric)
    if not isinstance(source_codes, list) or not source_codes:
        return None
    frappe = _frappe()
    get_all = getattr(frappe, "get_all", None)
    if get_all is None:
        return None
    account_rows = get_all(
        "Account",
        filters={
            "company": company,
            "account_number": ["like", "%"],
            "is_group": 0,
        },
        fields=["name", "account_number"],
        limit_page_length=0,
    )
    account_names = [
        row["name"]
        for row in account_rows
        if any(
            str(row.get("account_number") or "").startswith(str(code))
            for code in source_codes
        )
    ]
    if not account_names:
        return None
    filters: dict[str, Any] = {
        "company": company,
        "posting_date": ["between", [from_date, to_date]],
        "account": ["in", account_names],
        "is_cancelled": 0,
    }
    if finance_book:
        filters["finance_book"] = finance_book
    rows = get_all(
        "GL Entry",
        filters=filters,
        fields=["debit", "credit"],
        limit_page_length=0,
    )
    return sum(float(row.get("debit") or 0) - float(row.get("credit") or 0) for row in rows)


def _native_metric_activities(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    remark_like: str | None = None,
) -> dict[str, float]:
    """Read marked configured metric activity with one Account and one GL query."""
    metric_sources = _cash_flow_policy().get("metric_sources", {})
    if not isinstance(metric_sources, dict) or not metric_sources or not remark_like:
        return {}
    frappe = _frappe()
    get_all = getattr(frappe, "get_all", None)
    if get_all is None:
        return {}
    account_rows = get_all(
        "Account",
        filters={"company": company, "is_group": 0},
        fields=["name", "account_number"],
        limit_page_length=0,
    )
    account_numbers = {
        str(row["name"]): str(row.get("account_number") or "")
        for row in account_rows
        if row.get("name")
    }
    source_names = [
        name
        for name, account_number in account_numbers.items()
        if any(
            account_number.startswith(str(code))
            for codes in metric_sources.values()
            for code in codes
        )
    ]
    if not source_names:
        return {}
    filters: dict[str, Any] = {
        "company": company,
        "posting_date": ["between", [from_date, to_date]],
        "account": ["in", source_names],
        "is_cancelled": 0,
        "remarks": ["like", f"{remark_like}%"],
    }
    if finance_book:
        filters["finance_book"] = finance_book
    rows = get_all(
        "GL Entry",
        filters=filters,
        fields=["account", "debit", "credit"],
        limit_page_length=0,
    )
    deltas = {
        name: sum(
            float(row.get("debit") or 0) - float(row.get("credit") or 0)
            for row in rows
            if row.get("account") == name
        )
        for name in source_names
    }
    return {
        str(metric): sum(
            deltas.get(name, 0.0)
            for name, account_number in account_numbers.items()
            if any(account_number.startswith(str(code)) for code in codes)
        )
        for metric, codes in metric_sources.items()
    }


def _native_cash_flow_events(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Classify real cash GL movements using policy event rules.

    The cash line is the source of truth.  Counterpart accounts are used only
    to classify the voucher; a balance movement on an expense or liability
    account is never treated as cash paid by itself.
    """
    cash_policy = _cash_flow_policy()
    rules = cash_policy.get("event_rules", [])
    metric_sources = cash_policy.get("metric_sources", {})
    if not isinstance(rules, list) or not isinstance(metric_sources, dict):
        return {}, []
    frappe = _frappe()
    get_all = getattr(frappe, "get_all", None)
    if get_all is None:
        return {}, []
    account_rows = get_all(
        "Account",
        filters={"company": company, "is_group": 0},
        fields=["name", "account_number"],
        limit_page_length=0,
    )
    account_numbers = {
        str(row["name"]): str(row.get("account_number") or "")
        for row in account_rows
        if row.get("name")
    }
    cash_accounts = {
        name for name, code in account_numbers.items()
        if any(code.startswith(prefix) for prefix in ("111", "112", "113"))
    }
    if not cash_accounts:
        return {}, []
    filters: dict[str, Any] = {
        "company": company,
        "posting_date": ["between", [from_date, to_date]],
        "is_cancelled": 0,
    }
    if finance_book:
        if include_default_book_entries:
            default_book = str(
                frappe.get_cached_value("Company", company, "default_finance_book") or ""
            )
            books = {str(finance_book), ""}
            if default_book:
                books.add(default_book)
            filters["finance_book"] = ["in", sorted(books)]
        else:
            filters["finance_book"] = finance_book
    rows = get_all(
        "GL Entry",
        filters=filters,
        fields=[
            "name", "voucher_type", "voucher_no", "account", "debit", "credit",
            "cost_center", "posting_date",
        ],
        limit_page_length=0,
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row.get("voucher_type") or ""), str(row.get("voucher_no") or ""))
        grouped[key].append(dict(row))
    # Once the period's native cash ledger has been read, a metric with no
    # matching cash voucher is a traceable zero.  Unknown cash vouchers remain
    # exceptions and keep B03 fail-closed.
    metrics: dict[str, float] = {str(metric): 0.0 for metric in metric_sources}
    events: list[dict[str, Any]] = []
    for (voucher_type, voucher_no), voucher_rows in grouped.items():
        cash_rows = [row for row in voucher_rows if str(row.get("account")) in cash_accounts]
        if not cash_rows:
            continue
        cash_delta = sum(
            float(row.get("debit") or 0.0) - float(row.get("credit") or 0.0)
            for row in cash_rows
        )
        if abs(cash_delta) <= 0.0005:
            continue
        counterpart_codes = {
            account_numbers.get(str(row.get("account")), "")
            for row in voucher_rows
            if str(row.get("account")) not in cash_accounts
        }
        matched_rule: dict[str, Any] | None = None
        expected_direction = "inflow" if cash_delta > 0 else "outflow"
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("direction") != expected_direction:
                continue
            source_codes = [str(code) for code in rule.get("counterpart_account_codes", [])]
            if any(
                any(code.startswith(source_code) for source_code in source_codes)
                for code in counterpart_codes
            ):
                matched_rule = rule
                break
        if matched_rule is None:
            events.append({
                "status": "requires_classification",
                "voucher_type": voucher_type,
                "voucher_no": voucher_no,
                "cash_delta": round(cash_delta, 2),
                "counterpart_account_codes": sorted(code for code in counterpart_codes if code),
                "source_refs": [str(row.get("name")) for row in cash_rows if row.get("name")],
            })
            continue
        metric = str(matched_rule["metric"])
        amount = abs(cash_delta)
        if matched_rule["direction"] == "outflow":
            amount = -amount
        included_in_indirect = bool(matched_rule.get("include_in_indirect", True))
        if included_in_indirect:
            metrics[metric] = metrics.get(metric, 0.0) + amount
        events.append({
            "status": "derived",
            "metric": metric,
            "category": str(matched_rule["category"]),
            "amount": round(amount, 2),
            "included_in_indirect": included_in_indirect,
            "voucher_type": voucher_type,
            "voucher_no": voucher_no,
            "counterpart_account_codes": sorted(code for code in counterpart_codes if code),
            "source_refs": [str(row.get("name")) for row in cash_rows if row.get("name")],
        })
    return metrics, events


def _native_balance_metric(
    company: str,
    from_date: str,
    to_date: str,
    metric: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> float | None:
    """Return a balance-sheet change for an indirect-method metric."""
    source_codes = _cash_flow_policy().get("metric_sources", {}).get(metric)
    if not isinstance(source_codes, list) or not source_codes:
        return None
    balances, metadata = _native_account_balances(
        "balance_sheet",
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    opening = metadata.get("opening_balances") or {}
    if not isinstance(opening, dict):
        return None
    if not any(
        _mapped(str(code), {str(source_code) for source_code in source_codes})
        for code in set(balances) | set(opening)
    ):
        return None
    return _mapped_amount(balances, source_codes) - _mapped_amount(opening, source_codes)


def _native_pnl_metric(
    company: str,
    from_date: str,
    to_date: str,
    metric: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> float | None:
    """Return a P&L adjustment from the policy account sources."""
    source_codes = _cash_flow_policy().get("metric_sources", {}).get(metric)
    if not isinstance(source_codes, list) or not source_codes:
        return None
    balances, _metadata = _native_account_balances(
        "profit_and_loss",
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    if not any(
        _mapped(str(code), {str(source_code) for source_code in source_codes})
        for code in balances
    ):
        return None
    return _mapped_amount(balances, source_codes)


def _currency_policy() -> dict[str, Any]:
    """Return the reporting-currency policy used by every statement adapter."""
    reporting = _reporting_policy()
    currency = reporting.get("currency", {})
    if not isinstance(currency, dict):
        raise TypeError("shared.coa_template.reporting.currency must be a mapping")
    return currency


def _validate_accounting_currency(currency: str) -> None:
    """Fail closed when a Company currency is outside the approved VAS policy."""
    policy = _currency_policy()
    allowed = {str(item) for item in policy.get("allowed_accounting_currencies", [])}
    if currency not in allowed:
        _frappe().throw(
            f"Accounting currency {currency} is not allowed by the reporting policy",
            exc=_frappe().ValidationError,
        )
    if (
        policy.get("foreign_currency_transactions") == "disabled"
        and currency != policy.get("reporting_currency")
    ):
        _frappe().throw(
            "Foreign-currency accounting is disabled by the reporting policy",
            exc=_frappe().ValidationError,
        )


def _exchange_rate(source_currency: str, target_currency: str, rate_date: str) -> float:
    """Resolve a native ERPNext Exchange Rate for a future multi-currency policy."""
    if source_currency == target_currency:
        return 1.0
    policy = _currency_policy()
    if policy.get("translation") != "native_exchange_rate":
        raise ValueError(
            "Consolidation currency translation is not configured for non-reporting currencies"
        )
    from erpnext.setup.utils import get_exchange_rate

    rate = get_exchange_rate(source_currency, target_currency, rate_date)
    if not rate or float(rate) <= 0:
        raise ValueError(
            f"Missing native Exchange Rate {source_currency}/{target_currency} on {rate_date}"
        )
    return float(rate)


def _note_snapshot(note: dict[str, Any], statements: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve only quantitative note inputs that are already in native reports."""
    source = str(note.get("source") or "")
    if source == "policy":
        return {"source": "policy", "status": "derived", "data": {"framework": "VAS"}}
    if source == "profit_and_loss":
        return {
            "source": source,
            "status": "derived",
            "data": statements["profit_and_loss"].get("lines", []),
        }
    if source == "unmapped_accounts":
        return {
            "source": source,
            "status": "derived",
            "data": {
                statement: statements[statement].get("unmapped_account_codes", [])
                for statement in statements
            },
        }
    if source == "consolidation":
        return {
            "source": source,
            "status": "requires_consolidation_package",
            "data": None,
        }

    snapshots: dict[str, Any] = {}
    for reference in source.split("/"):
        statement_name, separator, line_code = reference.partition(".")
        if not separator or statement_name not in statements:
            continue
        line = next(
            (
                item
                for item in statements[statement_name].get("lines", [])
                if str(item.get("code")) == line_code
            ),
            None,
        )
        if line is not None:
            snapshots[reference] = {
                "code": line.get("code"),
                "name": line.get("name"),
                "amount": line.get("amount", 0.0),
            }
    if not snapshots:
        return None
    return {"source": source, "status": "derived", "data": snapshots}


def _mapped(code: str, mapped_codes: set[str]) -> bool:
    """Treat a TT99 parent account in policy as covering its descendants."""
    return any(code == candidate or code.startswith(candidate) for candidate in mapped_codes)


def _mapped_amount(balances: dict[str, float], account_codes: list[Any]) -> float:
    """Sum each native leaf balance covered by a policy Account range once."""
    mapped_codes = {str(code) for code in account_codes}
    return sum(
        amount
        for code, amount in balances.items()
        if _mapped(str(code), mapped_codes)
    )


def _mapped_abs_amount(balances: dict[str, float], account_codes: list[Any]) -> float:
    """Sum gross signed effects for all native leaves covered by an Account range."""
    mapped_codes = {str(code) for code in account_codes}
    return sum(
        abs(amount)
        for code, amount in balances.items()
        if _mapped(str(code), mapped_codes)
    )


STATUTORY_DETAIL_MARKER = "LETRON-STAT"


def _one_year_after(value: str) -> date:
    """Return the VAS current/non-current cutoff one year after a date."""
    current = date.fromisoformat(str(value))
    try:
        return current.replace(year=current.year + 1)
    except ValueError:  # 29 February
        return current.replace(year=current.year + 1, day=28)


def _native_statutory_detail_values(
    form_code: str,
    form: dict[str, Any],
    company: str,
    from_date: str,
    to_date: str,
    balances: dict[str, float],
    finance_book: str | None = None,
    as_of_date: str | None = None,
) -> dict[str, float | None]:
    """Resolve statutory account splits from native GL detail.

    ``Account`` balances intentionally do not contain maturity or subledger
    dimensions.  Maturity rows therefore use native ``GL Entry.due_date``;
    rows whose source is explicitly subledger-specific use the machine-readable
    ``LETRON-STAT|form=...|line=...`` marker in native GL remarks.  Missing
    detail remains ``None`` so the report never invents a classification.
    """
    frappe = _frappe()
    get_all = getattr(frappe, "get_all", None)
    if get_all is None:
        return {}
    account_rows = get_all(
        "Account",
        filters={"company": company, "is_group": 0},
        fields=["name", "account_number"],
        limit_page_length=0,
    )
    account_numbers = {
        str(row["name"]): str(row.get("account_number") or "")
        for row in account_rows
        if row.get("name")
    }
    rows_for_code = {
        name
        for name, account_number in account_numbers.items()
        if any(
            account_number.startswith(str(source_code))
            for line in form["lines"]
            if line["line_type"] == "account"
            for source_code in line.get("source_account_codes", [])
        )
    }
    if not rows_for_code:
        rows_for_code = set(account_numbers)

    result: dict[str, float | None] = {}
    detail_lines = [
        line
        for line in form["lines"]
        if line["line_type"] == "account"
        and (line.get("maturity") or line.get("source") == "subledger_classification_required")
    ]
    maturity_rows: list[dict[str, Any]] = []
    if any(line.get("maturity") for line in detail_lines):
        maturity_filters: dict[str, Any] = {
            "company": company,
            "posting_date": ["<=", as_of_date or to_date],
            "account": ["in", sorted(rows_for_code)],
            "is_cancelled": 0,
        }
        if finance_book:
            maturity_filters["finance_book"] = finance_book
        maturity_rows = get_all(
            "GL Entry",
            filters=maturity_filters,
            fields=["account", "debit", "credit", "due_date"],
            limit_page_length=0,
        )
    for line in detail_lines:
        code = str(line["code"])
        source_codes = [str(item) for item in line.get("source_account_codes", [])]
        base_amount = _mapped_amount(balances, source_codes)
        if not source_codes:
            result[code] = 0.0
            continue
        if line.get("maturity"):
            boundary = _one_year_after(as_of_date or to_date)
            amount = 0.0
            unknown = 0.0
            for row in maturity_rows:
                account_code = account_numbers.get(str(row.get("account")), "")
                if not any(account_code.startswith(source) for source in source_codes):
                    continue
                effect = _account_effect(
                    account_code,
                    "debit" if float(row.get("debit") or 0) else "credit",
                    abs(float(row.get("debit") or 0) - float(row.get("credit") or 0)),
                )
                if not row.get("due_date"):
                    unknown += abs(effect)
                    continue
                due_date = date.fromisoformat(str(row["due_date"])[:10])
                expected = line["maturity"] == "current"
                if (due_date <= boundary) == expected:
                    amount += effect
            result[code] = None if unknown > 0.0005 else amount
            if not maturity_rows and abs(base_amount) <= 0.0005:
                result[code] = 0.0
            continue

        marker = f"{STATUTORY_DETAIL_MARKER}|form={form_code}|line={code}"
        filters = {
            "company": company,
            "posting_date": ["between", [from_date, to_date]]
            if form_code == "B02-DN"
            else ["<=", as_of_date or to_date],
            "account": ["in", sorted(rows_for_code)],
            "remarks": ["like", f"%{marker}%"],
            "is_cancelled": 0,
        }
        if finance_book:
            filters["finance_book"] = finance_book
        rows = get_all(
            "GL Entry",
            filters=filters,
            fields=["account", "debit", "credit"],
            limit_page_length=0,
        )
        amount = 0.0
        for row in rows:
            account_code = account_numbers.get(str(row.get("account")), "")
            if not any(account_code.startswith(source) for source in source_codes):
                continue
            debit = float(row.get("debit") or 0)
            credit = float(row.get("credit") or 0)
            amount += _account_effect(
                account_code,
                "debit" if debit else "credit",
                abs(debit - credit),
            )
        result[code] = amount if rows else (0.0 if abs(base_amount) <= 0.0005 else None)
    return result


def _native_eps_metrics(
    company: str,
    from_date: str,
    to_date: str,
    profit_after_tax: float | None,
) -> tuple[dict[str, float], set[str]]:
    """Derive EPS from native Shareholder data where shares are configured.

    ERPNext has no native diluted-share instrument model.  Basic EPS is derived
    from the company's native Shareholder share balance; diluted EPS is marked
    not applicable until a dedicated native source exists.
    """
    del from_date, to_date
    frappe = _frappe()
    get_all = getattr(frappe, "get_all", None)
    get_doc = getattr(frappe, "get_doc", None)
    if get_all is None or get_doc is None or profit_after_tax is None:
        return {}, {"basic_eps", "diluted_eps"}
    shareholders = get_all(
        "Shareholder",
        filters={"company": company, "is_company": 1},
        pluck="name",
        limit_page_length=0,
    )
    shares = 0.0
    for name in shareholders:
        document = get_doc("Shareholder", name)
        shares += sum(float(row.get("no_of_shares") or 0) for row in document.share_balance)
    if shares <= 0:
        return {}, {"basic_eps", "diluted_eps"}
    return {"basic_eps": float(profit_after_tax) / shares}, {"diluted_eps"}


def _calculate_b02_period(
    form: dict[str, Any],
    company: str,
    from_date: str,
    to_date: str,
    balances: dict[str, float],
    finance_book: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Calculate one B02 period, including native EPS derivation."""
    classified_values = _native_statutory_detail_values(
        "B02-DN",
        form,
        company,
        from_date,
        to_date,
        balances,
        finance_book=finance_book,
        as_of_date=to_date,
    )
    lines, unresolved = _calculate_statutory_lines(
        form, balances, classified_values=classified_values
    )
    profit_after_tax = next(
        (
            float(line["amount"])
            for line in lines
            if line["code"] == "60"
            and line["amount"] is not None
            and line["status"] == "derived"
        ),
        None,
    )
    metric_values, not_applicable_metrics = _native_eps_metrics(
        company, from_date, to_date, profit_after_tax
    )
    if metric_values or not_applicable_metrics:
        lines, unresolved = _calculate_statutory_lines(
            form,
            balances,
            metric_values=metric_values,
            classified_values=classified_values,
            not_applicable_metrics=not_applicable_metrics,
        )
    return lines, unresolved


def _fiscal_year_for_range(company: str, from_date: str, to_date: str) -> str:
    """Resolve an enabled native Fiscal Year assigned to the Company."""
    frappe = _frappe()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(from_date)) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(to_date)
    ):
        frappe.throw("Reporting dates must use YYYY-MM-DD", exc=frappe.ValidationError)
    if from_date > to_date:
        frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
    fiscal_years = frappe.get_all(
        "Fiscal Year",
        filters={
            "year_start_date": ["<=", from_date],
            "year_end_date": [">=", to_date],
            "disabled": 0,
        },
        pluck="name",
        order_by="year_start_date asc",
        limit_page_length=0,
    )
    for name in fiscal_years:
        if frappe.db.exists(
            "Fiscal Year Company", {"parent": name, "company": company}
        ):
            return str(name)
    frappe.throw(
        f"No enabled Fiscal Year assigned to Company {company} covers {from_date} to {to_date}",
        exc=frappe.ValidationError,
    )
    raise AssertionError("unreachable")


def _native_account_balances_once(
    statement: str,
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Read Account rows through ERPNext's financial_statements engine."""
    frappe = _frappe()
    from erpnext.accounts.report.financial_statements import get_data, get_period_list

    period_list = get_period_list(None, None, from_date, to_date, "Date Range", "Yearly", accumulated_values=1, company=company)
    filters = frappe._dict({
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "period_start_date": from_date,
        "period_end_date": to_date,
        "filter_based_on": "Date Range",
        "periodicity": "Yearly",
        "accumulated_values": 1,
        "show_zero_values": 1,
        "finance_book": finance_book,
        "include_default_book_entries": int(include_default_book_entries),
    })
    roots = (("Asset", "Debit"), ("Liability", "Credit"), ("Equity", "Credit")) if statement == "balance_sheet" else (("Income", "Credit"), ("Expense", "Debit"))
    balances: dict[str, float] = {}
    opening_balances: dict[str, float] = {}
    for root_type, balance_must_be in roots:
        rows = get_data(company, root_type, balance_must_be, period_list, filters=filters, accumulated_values=1, only_current_fiscal_year=False, ignore_closing_entries=statement != "balance_sheet") or []
        for row in rows:
            code = row.get("acc_number")
            if code and not row.get("is_group"):
                balances[str(code)] = balances.get(str(code), 0.0) + float(row.get("total") or 0)
                opening_balances[str(code)] = opening_balances.get(str(code), 0.0) + float(row.get("opening_balance") or 0)
    return balances, {
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "opening_balances": opening_balances,
    }


def _combine_balance_maps(
    default_balances: dict[str, float],
    selected_balances: dict[str, float],
    blank_balances: dict[str, float],
) -> dict[str, float]:
    """Combine native Finance Book slices without counting blank rows twice."""
    codes = set(default_balances) | set(selected_balances) | set(blank_balances)
    return {
        code: default_balances.get(code, 0.0)
        + selected_balances.get(code, 0.0)
        - blank_balances.get(code, 0.0)
        for code in codes
    }


def _native_account_balances(
    statement: str,
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Read native balances, including a non-default adjustment book safely.

    ERPNext's financial-statement engine rejects a selected Finance Book plus
    ``include_default_book_entries`` when the selected book differs from the
    Company's configured default book. Read the three native scopes separately
    and subtract the blank-book overlap so the result remains one ledger view.
    """
    frappe = _frappe()
    _fiscal_year_for_range(company, from_date, to_date)
    if include_default_book_entries and finance_book:
        default_book = str(
            frappe.get_cached_value("Company", company, "default_finance_book") or ""
        )
        if default_book and default_book != str(finance_book):
            default_balances, default_metadata = _native_account_balances_once(
                statement,
                company,
                from_date,
                to_date,
                finance_book=default_book,
            )
            selected_balances, selected_metadata = _native_account_balances_once(
                statement,
                company,
                from_date,
                to_date,
                finance_book=finance_book,
            )
            blank_balances, blank_metadata = _native_account_balances_once(
                statement,
                company,
                from_date,
                to_date,
                finance_book="",
            )
            currencies = {
                str(metadata.get("currency") or "")
                for metadata in (default_metadata, selected_metadata, blank_metadata)
            }
            if len(currencies) != 1:
                frappe.throw(
                    "Native Finance Book slices returned inconsistent Company currencies",
                    exc=frappe.ValidationError,
                )
            default_opening = dict(default_metadata.get("opening_balances") or {})
            selected_opening = dict(selected_metadata.get("opening_balances") or {})
            blank_opening = dict(blank_metadata.get("opening_balances") or {})
            return _combine_balance_maps(
                default_balances,
                selected_balances,
                blank_balances,
            ), {
                "currency": next(iter(currencies), ""),
                "opening_balances": _combine_balance_maps(
                    default_opening,
                    selected_opening,
                    blank_opening,
                ),
            }

    return _native_account_balances_once(
        statement,
        company,
        from_date,
        to_date,
        finance_book=finance_book,
        include_default_book_entries=include_default_book_entries,
    )


def report(
    statement: str,
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> dict[str, Any]:
    """Return mapped VAS Balance Sheet or P&L from native ERPNext balances."""
    frappe = _frappe()
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Unknown Company: {company}", exc=frappe.DoesNotExistError)
    if from_date > to_date:
        frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
    lines = _mapping(statement)
    balances, native_metadata = _native_account_balances(
        statement,
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries,
    )
    _validate_accounting_currency(str(native_metadata["currency"]))
    mapped_codes = {str(code) for line in lines for code in line["account_codes"]}
    result = [{
        "code": line["code"],
        "name": line["name"],
        "amount": _mapped_amount(balances, line["account_codes"]),
        "classification": line.get("classification") or next((kind for kind, codes in _reporting_policy().get("statement_classification", {}).get(statement, {}).items() if line["code"] in codes), None),
    } for line in lines]
    unmapped = sorted(code for code in balances if not _mapped(code, mapped_codes) and abs(balances[code]) > 0.0005)
    return {"ok": not unmapped, "statement": statement, "company": company, "from_date": from_date, "to_date": to_date, "finance_book": finance_book, "currency": native_metadata["currency"], "mapping_version": _mapping_version(), "lines": result, "unmapped_account_codes": unmapped}


def native_cash_flow(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> dict[str, Any]:
    """Run the native Cash Flow report with the requested date range."""
    frappe = _frappe()
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Unknown Company: {company}", exc=frappe.DoesNotExistError)
    if from_date > to_date:
        frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
    from frappe.desk.query_report import run

    fiscal_year = _fiscal_year_for_range(company, from_date, to_date)
    currency = str(frappe.get_cached_value("Company", company, "default_currency"))
    _validate_accounting_currency(currency)
    native = run(report_name="Cash Flow", filters={"company": company, "from_fiscal_year": fiscal_year, "to_fiscal_year": fiscal_year, "filter_based_on": "Date Range", "period_start_date": from_date, "period_end_date": to_date, "periodicity": "Yearly", "accumulated_values": 1, "show_opening_and_closing_balance": 1, "finance_book": finance_book, "include_default_book_entries": int(include_default_book_entries)}, ignore_prepared_report=True)
    metadata = {
        "standard": _cash_flow_policy().get("standard", "VAS 24"),
        "method": _cash_flow_policy().get("method", "indirect"),
        "categories": _cash_flow_policy().get("categories", {}),
    }
    if isinstance(native, dict):
        return {
            **native,
            "ok": True,
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
            "finance_book": finance_book,
            "currency": currency,
            "cash_flow_policy": metadata,
        }
    return {
        "ok": True,
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "finance_book": finance_book,
        "currency": currency,
        "cash_flow_policy": metadata,
        "native": native,
    }


def _native_cash_flow_account_type_change(
    company: str,
    from_date: str,
    to_date: str,
    account_type: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
) -> float:
    """Read one native Cash Flow account-type bucket with ERPNext semantics."""
    from erpnext.accounts.report.cash_flow.cash_flow import (
        get_account_type_based_gl_data,
        get_period_list,
        get_start_date,
    )

    frappe = _frappe()
    period_list = get_period_list(
        None,
        None,
        from_date,
        to_date,
        "Date Range",
        "Yearly",
        accumulated_values=1,
        company=company,
    )
    filters = frappe._dict(
        {
            "company": company,
            "finance_book": finance_book,
            "include_default_book_entries": int(include_default_book_entries),
            "accumulated_values": 1,
        }
    )
    total = 0.0
    for period in period_list:
        filters.start_date = get_start_date(period, 1, company)
        filters.end_date = period["to_date"]
        filters.account_type = account_type
        amount = float(get_account_type_based_gl_data(company, filters) or 0.0)
        if account_type == "Depreciation":
            amount *= -1
        total += amount
    return total


def _cash_flow_metrics(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    include_default_book_entries: bool = False,
    _metric_marker: str | None = None,
) -> dict[str, Any]:
    """Return only B03 metrics that can be traced to native ERPNext data."""
    native = native_cash_flow(
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    profit_and_loss = report(
        "profit_and_loss",
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    pnl_amounts = {
        str(line["code"]): float(line["amount"] or 0.0)
        for line in profit_and_loss.get("lines", [])
        if line.get("amount") is not None
    }
    metrics: dict[str, float] = {
        "profit_before_tax": (
            pnl_amounts.get("E1", 0.0)
            - pnl_amounts.get("E2", 0.0)
            + pnl_amounts.get("E3", 0.0)
            - pnl_amounts.get("E4", 0.0)
            - pnl_amounts.get("E5", 0.0)
            - pnl_amounts.get("E6", 0.0)
            - pnl_amounts.get("E7", 0.0)
            - pnl_amounts.get("E8", 0.0)
            + pnl_amounts.get("E9", 0.0)
            - pnl_amounts.get("E10", 0.0)
        ),
        "depreciation": _native_cash_flow_account_type_change(
            company,
            from_date,
            to_date,
            "Depreciation",
            finance_book,
            include_default_book_entries,
        ),
        "receivables_change": _native_cash_flow_account_type_change(
            company,
            from_date,
            to_date,
            "Receivable",
            finance_book,
            include_default_book_entries,
        ),
        "inventory_change": _native_cash_flow_account_type_change(
            company,
            from_date,
            to_date,
            "Stock",
            finance_book,
            include_default_book_entries,
        ),
    }
    for metric in (
        "provisions",
        "payables_change_excluding_interest_and_tax",
        "prepaid_expense_change",
        "trading_securities_change",
    ):
        value = _native_balance_metric(
            company,
            from_date,
            to_date,
            metric,
            finance_book,
            include_default_book_entries,
        )
        if value is not None:
            metrics[metric] = value
    for metric in (
        "fx_revaluation",
        "investing_financing_gain_loss",
        "borrowing_cost",
        "other_operating_adjustments",
    ):
        value = _native_pnl_metric(
            company,
            from_date,
            to_date,
            metric,
            finance_book,
            include_default_book_entries,
        )
        if value is not None:
            metrics[metric] = value
    balances, balance_metadata = _native_account_balances(
        "balance_sheet",
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    opening_balances = balance_metadata.get("opening_balances") or {}
    metrics["opening_cash"] = _mapped_amount(opening_balances, ["111", "112", "113"])
    metrics["closing_cash"] = _mapped_amount(balances, ["111", "112", "113"])
    event_metrics, event_rows = _native_cash_flow_events(
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
    )
    metrics.update(event_metrics)
    for metric, activity in _native_metric_activities(
        company, from_date, to_date, finance_book, remark_like=_metric_marker
    ).items():
        # The marker is retained only for rollback-only acceptance fixtures.
        # Production derives these values from real cash GL events above.
        if _metric_marker:
            metrics[metric] = activity
    if "translation_fx_effect" not in metrics:
        metrics["translation_fx_effect"] = 0.0
    return {
        "metrics": metrics,
        "native": native,
        "unmapped_account_codes": list(profit_and_loss.get("unmapped_account_codes", [])),
        "currency": balance_metadata["currency"],
        "cash_flow_events": event_rows,
        "cash_flow_exceptions": [
            event for event in event_rows if event.get("status") != "derived"
        ],
    }


def unmapped_accounts(company: str, from_date: str, to_date: str, finance_book: str | None = None) -> dict[str, Any]:
    """Return non-zero ledger accounts not covered by the policy mapping."""
    balances: dict[str, float] = {}
    for statement in ("balance_sheet", "profit_and_loss"):
        current, _metadata = _native_account_balances(statement, company, from_date, to_date, finance_book)
        balances.update({code: balances.get(code, 0.0) + amount for code, amount in current.items()})
    mapped = {str(code) for statement in ("balance_sheet", "profit_and_loss") for line in _mapping(statement) for code in line["account_codes"]}
    rows = [{"account_code": code, "amount": amount} for code, amount in sorted(balances.items()) if abs(amount) > 0.0005 and not _mapped(code, mapped)]
    return {"ok": not rows, "company": company, "from_date": from_date, "to_date": to_date, "finance_book": finance_book, "currency": _frappe().get_cached_value("Company", company, "default_currency"), "accounts": rows}


def notes(company: str, from_date: str, to_date: str, finance_book: str | None = None) -> dict[str, Any]:
    """Return the VAS notes data envelope; note text remains accounting-owned."""
    statements = {
        statement: report(statement, company, from_date, to_date, finance_book)
        for statement in ("balance_sheet", "profit_and_loss")
    }
    reporting = _reporting_policy()
    note_rows = []
    for note in reporting.get("disclosure_notes", []):
        if not isinstance(note, dict) or not note.get("code"):
            continue
        snapshot = _note_snapshot(note, statements)
        note_rows.append({
            **note,
            "status": snapshot["status"] if snapshot else "template",
            "data": snapshot["data"] if snapshot else None,
        })
    return {
        "ok": all(value["ok"] for value in statements.values()),
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "finance_book": finance_book,
        "currency": _frappe().get_cached_value("Company", company, "default_currency"),
        "policy": reporting,
        "notes": note_rows,
        "note_status": {note["code"]: note["status"] for note in note_rows},
        "statement_data": statements,
    }


def b09_report(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    comparative_from_date: str | None = None,
    comparative_to_date: str | None = None,
) -> dict[str, Any]:
    """Return a structured, source-backed B09-DN preview.

    Accounting-owned narrative is intentionally not invented here.  It is
    completed on a ``Letron VAS Report Package`` before the package can be
    issued.
    """
    statements = {
        statement: report(statement, company, from_date, to_date, finance_book)
        for statement in ("balance_sheet", "profit_and_loss")
    }
    form = _statutory_form("B09-DN")
    note_rows: list[dict[str, Any]] = []
    for definition in form["lines"]:
        source = str(definition.get("source") or "")
        note = {"code": definition["code"], "name": definition["name"], "source": source}
        snapshot = _note_snapshot(note, statements)
        if snapshot:
            status = str(snapshot["status"])
            data = snapshot.get("data")
            source_refs = [source]
        elif source == "accounting_input":
            status = "requires_accounting_input"
            data = None
            source_refs = []
        else:
            status = "requires_source"
            data = None
            source_refs = []
        note_rows.append({
            **note,
            "required": bool(definition.get("required", True)),
            "status": status,
            "data": data,
            "source_refs": source_refs,
        })
    existing_package: dict[str, Any] | None = None
    frappe = _frappe()
    if frappe.db.exists("DocType", "Letron VAS Report Package"):
        rows = frappe.get_all(
            "Letron VAS Report Package",
            filters={
                "company": company,
                "form_code": "B09-DN",
                "from_date": from_date,
                "to_date": to_date,
            },
            fields=["name", "status", "policy_version", "policy_hash", "source_cutoff", "validation_json"],
            order_by="modified desc",
            limit_page_length=1,
        )
        if rows:
            existing_package = dict(rows[0])
            note_rows_from_package = frappe.get_all(
                "Letron VAS Report Note",
                filters={"parent": existing_package["name"]},
                fields=["code", "status", "data_json", "source_refs"],
                limit_page_length=0,
            )
            persisted_notes = {
                str(row.get("code")): row for row in note_rows_from_package
            }
            for note in note_rows:
                persisted = persisted_notes.get(str(note["code"]))
                if not persisted:
                    continue
                if persisted.get("status"):
                    note["status"] = str(persisted["status"])
                if persisted.get("data_json"):
                    try:
                        note["data"] = json.loads(str(persisted["data_json"]))
                    except json.JSONDecodeError:
                        note["status"] = "requires_source"
                if persisted.get("source_refs"):
                    try:
                        note["source_refs"] = json.loads(str(persisted["source_refs"]))
                    except json.JSONDecodeError:
                        note["source_refs"] = []
    complete = all(
        not row["required"] or row["status"] == "derived"
        for row in note_rows
    ) and all(value.get("ok") is True for value in statements.values())
    return {
        "ok": complete,
        "publishable": complete
        and existing_package is not None
        and existing_package.get("status") == "Closed"
        and json.loads(str(existing_package.get("validation_json") or "{}")).get("ok") is True,
        "form_code": "B09-DN",
        "form_name": form["name"],
        "statement": "notes",
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "finance_book": finance_book,
        "comparative_period": {
            "from_date": comparative_from_date,
            "to_date": comparative_to_date,
        } if comparative_from_date and comparative_to_date else None,
        "currency": frappe.get_cached_value("Company", company, "default_currency"),
        "mapping_version": _mapping_version(),
        "columns": form["columns"],
        "notes": note_rows,
        "status": "derived" if complete else "incomplete",
        "package": existing_package,
        "source": "native_gl_and_accounting_input",
        "statement_data": statements,
    }


def create_b09_package(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    accounting_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a draft B09 package for accounting review in native ERPNext."""
    frappe = _frappe()
    frappe.has_permission("Letron VAS Report Package", "create", throw=True)
    from letron_api.control.policy import load_policy

    policy = load_policy()
    canonical = json.dumps(policy, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    preview = b09_report(company, from_date, to_date, finance_book)
    inputs = accounting_inputs or {}
    notes_rows = []
    for row in preview["notes"]:
        supplied = inputs.get(str(row["code"]))
        supplied_data = supplied
        supplied_refs = row["source_refs"]
        if isinstance(supplied, dict) and "data" in supplied:
            supplied_data = supplied.get("data")
            supplied_refs = supplied.get("source_refs") or row["source_refs"]
        if supplied is not None:
            row["data"] = supplied_data
            row["status"] = "derived"
            row["source_refs"] = [str(value) for value in supplied_refs]
        notes_rows.append({
            "code": row["code"],
            "title": row["name"],
            "source": row["source"],
            "data_json": json.dumps(row["data"], ensure_ascii=False, sort_keys=True),
            "status": row["status"],
            "source_refs": json.dumps(row["source_refs"], ensure_ascii=False),
        })
    complete = all(
        not row["required"] or row["status"] == "derived"
        for row in preview["notes"]
    )
    validation = {
        "ok": complete and all(
            value.get("ok") is True for value in preview["statement_data"].values()
        ),
        "statement_ok": all(
            value.get("ok") is True for value in preview["statement_data"].values()
        ),
        "unresolved": [row["code"] for row in preview["notes"] if row["status"] != "derived"],
        "reconciliation_checks": [],
    }
    doc = frappe.get_doc({
        "doctype": "Letron VAS Report Package",
        "company": company,
        "form_code": "B09-DN",
        "from_date": from_date,
        "to_date": to_date,
        "accounting_currency": preview["currency"],
        "reporting_currency": _currency_policy().get("reporting_currency"),
        "policy_version": int(policy.get("version", 0)),
        "policy_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source_cutoff": frappe.utils.now_datetime(),
        "status": "Draft",
        "validation_json": json.dumps(validation, ensure_ascii=False, sort_keys=True),
        "lines_json": json.dumps(preview["notes"], ensure_ascii=False, sort_keys=True),
        "notes": notes_rows,
    })
    doc.insert()
    return doc.as_dict()


def _consolidation_settings() -> dict[str, Any]:
    from letron_api.control.policy import load_policy

    return dict(load_policy().get("shared", {}).get("consolidation", {}))


def _configured_companies(companies: list[str]) -> list[str]:
    settings = _consolidation_settings()
    configured = [str(item) for item in settings.get("companies", [])]
    if not configured or set(companies) != set(configured) or len(companies) != len(configured):
        _frappe().throw("Consolidation must cover exactly the seven policy Companies", exc=_frappe().ValidationError)
    return configured


def _account_code(account: str) -> str | None:
    value = _frappe().db.get_value("Account", account, "account_number")
    return str(value) if value else None


def _matched_account_amounts(
    rows: list[dict[str, Any]], account_codes: list[Any]
) -> list[dict[str, Any]]:
    """Return gross matched amounts by actual native Account code.

    Policy rules may name an Account family (for example ``136``), while a
    posted GL row normally uses a leaf such as ``1368``.  Consolidation
    adjustments must retain that leaf code; posting to the family could target
    a native group Account and would also lose the audit trail to the source
    ledger.  Amounts are allocated once, in stable code order, so one source
    Account cannot be reused against multiple counterparty Accounts.
    """
    effects: dict[str, float] = defaultdict(float)
    for row in rows:
        code = row.get("account_code")
        if not code:
            continue
        effects[str(code)] += float(row.get("debit") or 0) - float(row.get("credit") or 0)
    return [
        {"account_code": code, "amount": abs(amount)}
        for code, amount in sorted(effects.items())
        if abs(amount) > 0.0005
        and any(
            code == str(candidate) or code.startswith(str(candidate))
            for candidate in account_codes
        )
    ]


_MARKER_FIELDS = (
    "matching_id",
    "source_company",
    "counterparty_company",
    "transaction_type",
)


def _compile_intercompany_marker(template: str) -> re.Pattern[str]:
    """Compile the policy marker as a literal template with bounded fields."""
    if not isinstance(template, str) or not template.strip():
        raise ValueError("shared.consolidation.intercompany_marker must be non-empty")
    pattern = re.escape(template)
    for field in _MARKER_FIELDS:
        placeholder = re.escape("{" + field + "}")
        # Company names may contain spaces (for example ``Letron Holding``),
        # while identifiers and transaction types stay token-like.  The
        # literal ``|`` separators are the boundary for company values.
        value_pattern = (
            r"[A-Za-z0-9_.-]+"
            if field in {"matching_id", "transaction_type"}
            else r"[^|]+?"
        )
        pattern = pattern.replace(placeholder, rf"(?P<{field}>{value_pattern})")
    return re.compile(pattern)


def _intercompany_marker_pattern() -> re.Pattern[str]:
    template = _consolidation_settings().get("intercompany_marker")
    return _compile_intercompany_marker(str(template or ""))


def _parse_intercompany_marker(value: Any, pattern: re.Pattern[str] | None = None) -> dict[str, str] | None:
    match = (pattern or _intercompany_marker_pattern()).search(str(value or ""))
    if not match:
        return None
    return {field: str(match.group(field)).strip() for field in _MARKER_FIELDS}


def _render_intercompany_marker(
    matching_id: str,
    source_company: str,
    counterparty_company: str,
    transaction_type: str,
) -> str:
    """Render the policy marker used on both source vouchers and GL rows."""
    settings = _consolidation_settings()
    companies = {str(company) for company in settings.get("companies", [])}
    values = {
        "matching_id": matching_id,
        "source_company": source_company,
        "counterparty_company": counterparty_company,
        "transaction_type": transaction_type,
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("intercompany marker values must be non-empty strings")
    if source_company not in companies or counterparty_company not in companies:
        raise ValueError("intercompany marker companies must be in consolidation policy")
    if source_company == counterparty_company:
        raise ValueError("intercompany marker companies must be different")
    for field in ("matching_id", "transaction_type"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", values[field]):
            raise ValueError(f"intercompany marker {field} is invalid")
    template = settings.get("intercompany_marker")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("shared.consolidation.intercompany_marker must be non-empty")
    return template.format(**values)


def _is_balanced_intercompany_match(item: dict[str, Any], companies: list[str]) -> bool:
    rows = item.get("rows") or []
    actual_companies = {str(value) for value in item.get("companies", [])}
    counterparties = {str(value) for value in item.get("counterparties", [])}
    pairs = {
        (str(row.get("company")), str(row.get("counterparty_company")))
        for row in rows
    }
    allowed_pairs = {
        (source, counterparty)
        for source in actual_companies
        for counterparty in counterparties
        if source != counterparty and counterparty in companies
    }
    transaction_types = {str(row.get("transaction_type")) for row in rows}
    source_markers_valid = all(
        str(row.get("source_company")) == str(row.get("company"))
        and str(row.get("source_company")) in companies
        for row in rows
    )
    structure_balanced = (
        len(actual_companies) == 2
        and len(rows) >= 2
        and pairs == allowed_pairs
        and len(transaction_types) == 1
        and source_markers_valid
    )
    if not structure_balanced:
        return False

    # Native GL rows should represent a balanced source voucher for each
    # directed Company pair.  Gross debit and credit are deliberately checked
    # separately: net debit-credit is zero for a normal balanced Journal Entry
    # and would therefore hide an asymmetric 1,000-versus-500 pair.
    if all("debit" in row and "credit" in row for row in rows):
        totals: dict[tuple[str, str], tuple[float, float]] = {}
        for row in rows:
            pair = (str(row.get("company")), str(row.get("counterparty_company")))
            debit, credit = totals.get(pair, (0.0, 0.0))
            totals[pair] = (
                debit + float(row.get("debit") or 0),
                credit + float(row.get("credit") or 0),
            )
        if set(totals) != pairs:
            return False
        pair_values = list(totals.values())
        if any(abs(debit - credit) > 0.0005 for debit, credit in pair_values):
            return False
        gross = [debit + credit for debit, credit in pair_values]
        if any(value <= 0.0005 for value in gross) or abs(gross[0] - gross[1]) > 0.0005:
            return False
    return True


def intercompany_matches(companies: list[str], from_date: str, to_date: str) -> list[dict[str, Any]]:
    """Match explicitly marked GL lines; unmarked transactions are never guessed."""
    frappe = _frappe()
    # Use the permission-aware query path.  The public route checks DocType
    # permission before entering this function, but ``get_all`` would still
    # bypass row-level User Permissions and could expose another Company's GL
    # to a restricted operator.
    rows = frappe.get_list(
        "GL Entry",
        filters={"company": ["in", companies], "posting_date": ["between", [from_date, to_date]], "is_cancelled": 0},
        fields=["name", "company", "account", "debit", "credit", "posting_date", "voucher_type", "voucher_no", "remarks"],
        limit_page_length=0,
    )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        marker = _parse_intercompany_marker(row.get("remarks"))
        if not marker:
            continue
        matching_id = marker["matching_id"]
        source_company = marker["source_company"]
        counterparty = marker["counterparty_company"]
        transaction_type = marker["transaction_type"]
        item = groups.setdefault(matching_id, {"matching_id": matching_id, "counterparties": set(), "companies": set(), "transaction_type": transaction_type, "rows": []})
        item["counterparties"].add(counterparty)
        item["companies"].add(str(row.company))
        item["rows"].append({
            **row,
            "account_code": _account_code(row.account),
            "source_company": source_company,
            "counterparty_company": counterparty,
            "transaction_type": transaction_type,
        })
    result = []
    for item in groups.values():
        item["counterparties"] = sorted(item["counterparties"])
        item["companies"] = sorted(item["companies"])
        item["balanced"] = _is_balanced_intercompany_match(item, companies)
        result.append(item)
    return sorted(result, key=lambda value: value["matching_id"])


def elimination_schedule(companies: list[str], from_date: str, to_date: str) -> list[dict[str, Any]]:
    settings = _consolidation_settings()
    matches = intercompany_matches(companies, from_date, to_date)
    schedule: list[dict[str, Any]] = []
    for match in matches:
        if not match["balanced"]:
            continue
        for rule in settings.get("elimination_rules", []):
            posting_mode = rule.get("posting_mode", "policy_accounts")
            if posting_mode == "mirror_actual_accounts":
                source_accounts = _matched_account_amounts(
                    match["rows"], rule["source_account_codes"]
                )
                counterparty_accounts = _matched_account_amounts(
                    match["rows"], rule["counterparty_account_codes"]
                )
                for source_account in source_accounts:
                    for counterparty_account in counterparty_accounts:
                        amount = min(
                            float(source_account["amount"]),
                            float(counterparty_account["amount"]),
                        )
                        if amount <= 0.0005:
                            continue
                        schedule.append(
                            {
                                "rule_code": rule["code"],
                                "matching_id": match["matching_id"],
                                "source_companies": match["companies"],
                                "counterparties": match["counterparties"],
                                "source_account_code": source_account["account_code"],
                                "counterparty_account_code": counterparty_account[
                                    "account_code"
                                ],
                                "debit_account_code": counterparty_account[
                                    "account_code"
                                ],
                                "credit_account_code": source_account["account_code"],
                                "amount": round(amount, 2),
                                "transaction_type": match["transaction_type"],
                            }
                        )
                        source_account["amount"] = float(source_account["amount"]) - amount
                        counterparty_account["amount"] = (
                            float(counterparty_account["amount"]) - amount
                        )
                        if source_account["amount"] <= 0.0005:
                            break
                    if source_account["amount"] <= 0.0005:
                        continue
            else:
                codes = defaultdict(float)
                for row in match["rows"]:
                    if row.get("account_code"):
                        codes[str(row["account_code"])] += float(
                            row.get("debit") or 0
                        ) - float(row.get("credit") or 0)
                source = _mapped_abs_amount(codes, rule["source_account_codes"])
                counterparty = _mapped_abs_amount(
                    codes, rule["counterparty_account_codes"]
                )
                amount = min(source, counterparty)
                if amount <= 0.0005:
                    continue
                schedule.append(
                    {
                        "rule_code": rule["code"],
                        "matching_id": match["matching_id"],
                        "source_companies": match["companies"],
                        "counterparties": match["counterparties"],
                        "debit_account_code": rule["debit_account_code"],
                        "credit_account_code": rule["credit_account_code"],
                        "amount": round(amount, 2),
                        "transaction_type": match["transaction_type"],
                    }
                )
    return schedule


def _account_root_type_from_policy(account_code: str) -> str | None:
    """Resolve the normal balance of a policy account without touching GL."""
    from letron_api.control.policy import load_policy

    accounts = load_policy().get("shared", {}).get("coa_template", {}).get("accounts", [])
    candidates = [
        item
        for item in accounts
        if str(account_code).startswith(str(item.get("code", "")))
    ]
    if not candidates:
        return None
    return str(max(candidates, key=lambda item: len(str(item.get("code", "")))).get("root_type"))


def _account_effect(account_code: str, side: str, amount: float) -> float:
    """Return the signed statement effect of a debit or credit posting."""
    root_type = _account_root_type_from_policy(account_code)
    if root_type is None:
        return 0.0
    debit_normal = root_type in {"Asset", "Expense"}
    is_debit = side == "debit"
    return amount if is_debit == debit_normal else -amount


def _line_for_account(lines: list[dict[str, Any]], account_code: str) -> dict[str, Any] | None:
    """Find the most specific mapped statement line for an Account code."""
    candidates = [
        line
        for line in lines
        if any(
            account_code == str(code) or account_code.startswith(str(code))
            for code in line.get("account_codes", [])
        )
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda line: max(
            (len(str(code)) for code in line.get("account_codes", []) if account_code == str(code) or account_code.startswith(str(code))),
            default=0,
        ),
    )


def _aggregate_statement(
    statement: str,
    company_reports: dict[str, dict[str, Any]],
    companies: list[str],
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    """Aggregate the native statutory report lines without writing a ledger row."""
    lines_by_code = {
        str(line["code"]): {
            "code": line["code"],
            "name": line["name"],
            "amount": 0.0,
            "classification": line.get("classification")
            or next(
                (
                    kind
                    for kind, codes in _reporting_policy()
                    .get("statement_classification", {})
                    .get(statement, {})
                    .items()
                    if line["code"] in codes
                ),
                None,
            ),
        }
        for line in _mapping(statement)
    }
    unmapped: set[str] = set()
    currencies: set[str] = set()
    conversion_rates: dict[str, float] = {}
    target_currency = str(_currency_policy().get("reporting_currency") or "")
    for company in companies:
        payload = company_reports[company][statement]
        source_currency = str(payload.get("currency") or "")
        currencies.add(source_currency)
        rate = _exchange_rate(source_currency, target_currency, to_date)
        conversion_rates[source_currency] = rate
        unmapped.update(str(code) for code in payload.get("unmapped_account_codes", []))
        for line in payload.get("lines", []):
            code = str(line.get("code"))
            if code in lines_by_code:
                current_amount = float(lines_by_code[code].get("amount") or 0)
                lines_by_code[code]["amount"] = current_amount + float(line.get("amount") or 0) * rate
    currency = target_currency or next(iter(currencies - {""}), None)
    return {
        "ok": not unmapped,
        "statement": statement,
        "from_date": from_date,
        "to_date": to_date,
        "currency": currency,
        "currency_conversion": {
            "reporting_currency": currency,
            "rates": conversion_rates,
            "rate_date": to_date,
        },
        "mapping_version": _mapping_version(),
        "lines": list(lines_by_code.values()),
        "unmapped_account_codes": sorted(unmapped),
    }


def _apply_elimination_schedule(
    statement: str,
    base: dict[str, Any],
    schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate a pro-forma post-elimination view; never writes GL."""
    lines = [dict(line) for line in base["lines"]]
    impact: list[dict[str, Any]] = []
    unmapped = set(base.get("unmapped_account_codes", []))
    for item in schedule:
        for side in ("debit", "credit"):
            account_code = str(item[f"{side}_account_code"])
            line = _line_for_account(_mapping(statement), account_code)
            effect = _account_effect(account_code, side, float(item["amount"]))
            if line is None:
                unmapped.add(account_code)
                continue
            target = next(row for row in lines if row["code"] == line["code"])
            target["amount"] = round(float(target.get("amount") or 0) + effect, 2)
            impact.append(
                {
                    "statement": statement,
                    "line_code": line["code"],
                    "account_code": account_code,
                    "side": side,
                    "amount": round(effect, 2),
                    "matching_id": item["matching_id"],
                    "rule_code": item["rule_code"],
                }
            )
    return {
        **base,
        "ok": not unmapped,
        "lines": lines,
        "unmapped_account_codes": sorted(unmapped),
        "elimination_impacts": impact,
    }


def _aggregate_cash_flow(
    company_reports: dict[str, dict[str, Any]],
    companies: list[str],
    from_date: str,
    to_date: str,
    comparative_from_date: str | None = None,
    comparative_to_date: str | None = None,
) -> dict[str, Any]:
    """Aggregate B03 lines with the correct closing rate for each period."""
    if (comparative_from_date is None) != (comparative_to_date is None):
        _frappe().throw(
            "comparative_from_date and comparative_to_date must be provided together",
            exc=_frappe().ValidationError,
        )
    form = _statutory_form("B03-DN")
    line_totals: dict[str, float] = defaultdict(float)
    line_comparative_totals: dict[str, float] = defaultdict(float)
    line_statuses: dict[str, set[str]] = defaultdict(set)
    comparative_statuses: dict[str, set[str]] = defaultdict(set)
    unmapped: set[str] = set()
    rates: dict[str, float] = {}
    comparative_rates: dict[str, float] = {}
    target_currency = str(_currency_policy().get("reporting_currency") or "")
    for company in companies:
        payload = company_reports[company]["cash_flow"]
        source_currency = str(payload.get("currency") or "")
        rate = _exchange_rate(source_currency, target_currency, to_date)
        comparative_rate = (
            _exchange_rate(source_currency, target_currency, comparative_to_date)
            if comparative_to_date
            else rate
        )
        rates[source_currency] = rate
        if comparative_to_date:
            comparative_rates[source_currency] = comparative_rate
        unmapped.update(str(code) for code in payload.get("unmapped_account_codes", []))
        for line in payload.get("lines", []):
            code = str(line.get("code"))
            status = str(line.get("status") or "requires_metric")
            line_statuses[code].add(status)
            if line.get("amount") is not None:
                line_totals[code] += float(line["amount"]) * rate
            else:
                line_statuses[code].add("requires_metric")
            comparative_status = str(
                line.get("comparative_status") or "not_requested"
            )
            comparative_statuses[code].add(comparative_status)
            if line.get("comparative_amount") is not None:
                line_comparative_totals[code] += float(line["comparative_amount"]) * comparative_rate

    output_lines: list[dict[str, Any]] = []
    for definition in form["lines"]:
        code = str(definition["code"])
        statuses = line_statuses.get(code, {"requires_metric"})
        comparative = comparative_statuses.get(code, {"not_requested"})
        status = (
            "derived"
            if statuses == {"derived"}
            else next(
                (
                    candidate
                    for candidate in (
                        "requires_comparative_period",
                        "requires_metric",
                        "requires_classification",
                        "requires_other",
                    )
                    if candidate in statuses
                ),
                min(statuses),
            )
        )
        comparative_status = (
            "derived"
            if comparative == {"derived"}
            else next(
                (
                    candidate
                    for candidate in (
                        "requires_comparative_period",
                        "requires_metric",
                        "requires_classification",
                        "requires_other",
                    )
                    if candidate in comparative
                ),
                min(comparative),
            )
        )
        output_lines.append(
            {
                "code": definition["code"],
                "name": definition["name"],
                "line_type": definition["line_type"],
                "amount": round(line_totals[code], 2) if status == "derived" else None,
                "status": status,
                "comparative_amount": (
                    round(line_comparative_totals[code], 2)
                    if comparative_status == "derived"
                    else None
                ),
                "comparative_status": comparative_status,
            }
        )
    unresolved = [line["code"] for line in output_lines if line["status"] != "derived"]
    return {
        "ok": not unresolved and not unmapped,
        "form_code": "B03-DN",
        "form_name": form["name"],
        "statement": "cash_flow",
        "from_date": from_date,
        "to_date": to_date,
        "currency": target_currency,
        "currency_conversion": {
            "reporting_currency": target_currency,
            "rates": rates,
            "rate_date": to_date,
        },
        "comparative_currency_conversion": (
            {
                "reporting_currency": target_currency,
                "rates": comparative_rates,
                "rate_date": comparative_to_date,
            }
            if comparative_to_date
            else None
        ),
        "mapping_version": _mapping_version(),
        "columns": form["columns"],
        "lines": output_lines,
        "unresolved_line_codes": unresolved,
        "unmapped_account_codes": sorted(unmapped),
    }


def _consolidation_cost_center(holding: str) -> str:
    """Select a leaf Cost Center for the Holding adjustment JE."""
    frappe = _frappe()
    from letron_api.control.policy import load_policy

    shared = load_policy().get("shared", {})
    configured = next(
        (
            item
            for item in shared.get("cost_centers", [])
            if item.get("company") == holding and "FIN" in item.get("functions", [])
        ),
        None,
    )
    if configured:
        expected = f"{configured['code']}-FIN"
        candidate = frappe.db.get_value(
            "Cost Center",
            {"company": holding, "cost_center_name": expected, "is_group": 0},
            "name",
        )
        if candidate:
            return str(candidate)
    candidates = frappe.get_all(
        "Cost Center",
        filters={"company": holding, "is_group": 0, "disabled": 0},
        fields=["name"],
        order_by="name asc",
        limit_page_length=1,
    )
    if candidates:
        return str(candidates[0].name)
    frappe.throw(
        f"Missing leaf consolidation Cost Center for {holding}",
        exc=frappe.ValidationError,
    )
    raise AssertionError("unreachable")


def consolidation_package(
    companies: list[str],
    from_date: str,
    to_date: str,
    include_adjustments: bool = False,
    comparative_from_date: str | None = None,
    comparative_to_date: str | None = None,
) -> dict[str, Any]:
    """Build native company reports and a deterministic pro-forma group view."""
    if not companies:
        raise ValueError("companies must not be empty")
    if (comparative_from_date is None) != (comparative_to_date is None):
        _frappe().throw(
            "comparative_from_date and comparative_to_date must be provided together",
            exc=_frappe().ValidationError,
        )
    if comparative_from_date and comparative_to_date and comparative_from_date > comparative_to_date:
        _frappe().throw(
            "comparative_from_date must not be after comparative_to_date",
            exc=_frappe().ValidationError,
        )
    settings = _consolidation_settings()
    companies = _configured_companies(companies)
    holding_setting = settings.get("holding_company")
    if not isinstance(holding_setting, str) or not holding_setting:
        _frappe().throw(
            "Consolidation policy must define a holding company",
            exc=_frappe().ValidationError,
        )
    holding = str(holding_setting)
    packages = {}
    for company in companies:
        packages[company] = {
            statement: report(statement, company, from_date, to_date)
            for statement in ("balance_sheet", "profit_and_loss")
        }
        packages[company]["cash_flow"] = statutory_cash_flow(
            company,
            from_date,
            to_date,
            comparative_from_date=comparative_from_date,
            comparative_to_date=comparative_to_date,
            _require_comparative=False,
        )
        if comparative_from_date and comparative_to_date:
            packages[company]["comparative"] = {
                statement: report(
                    statement,
                    company,
                    comparative_from_date,
                    comparative_to_date,
                )
                for statement in ("balance_sheet", "profit_and_loss")
            }
    schedule = elimination_schedule(companies, from_date, to_date)
    before = {
        statement: _aggregate_statement(statement, packages, companies, from_date, to_date)
        for statement in ("balance_sheet", "profit_and_loss")
    }
    after = {
        statement: _apply_elimination_schedule(statement, before[statement], schedule)
        for statement in ("balance_sheet", "profit_and_loss")
    }
    consolidated_cash_flow = _aggregate_cash_flow(
        packages,
        companies,
        from_date,
        to_date,
        comparative_from_date=comparative_from_date,
        comparative_to_date=comparative_to_date,
    )
    result: dict[str, Any] = {
        "ok": all(statement["ok"] for statement in after.values())
        and consolidated_cash_flow["ok"],
        "holding_company": holding,
        "finance_book": settings.get("finance_book"),
        "companies": packages,
        "from_date": from_date,
        "to_date": to_date,
        "intercompany_matches": intercompany_matches(companies, from_date, to_date),
        "elimination_schedule": schedule,
        "consolidated_before_elimination": before,
        "consolidated_after_elimination": after,
        "consolidated_cash_flow": consolidated_cash_flow,
        "elimination_mode": "native_journal_entry_on_holding_finance_book",
    }
    if comparative_from_date and comparative_to_date:
        comparative_packages = {
            company: packages[company]["comparative"]
            for company in companies
        }
        comparative_schedule = elimination_schedule(
            companies, comparative_from_date, comparative_to_date
        )
        comparative_before = {
            statement: _aggregate_statement(
                statement,
                comparative_packages,
                companies,
                comparative_from_date,
                comparative_to_date,
            )
            for statement in ("balance_sheet", "profit_and_loss")
        }
        comparative_after = {
            statement: _apply_elimination_schedule(
                statement, comparative_before[statement], comparative_schedule
            )
            for statement in ("balance_sheet", "profit_and_loss")
        }
        result.update(
            {
                "comparative_from_date": comparative_from_date,
                "comparative_to_date": comparative_to_date,
                "comparative_elimination_schedule": comparative_schedule,
                "consolidated_before_elimination_comparative": comparative_before,
                "consolidated_after_elimination_comparative": comparative_after,
            }
        )
    if include_adjustments:
        adjustment_book = str(settings.get("finance_book") or "")
        if not adjustment_book:
            _frappe().throw(
                "Consolidation adjustment Finance Book is not configured",
                exc=_frappe().ValidationError,
            )
        native_packages = dict(packages)
        native_packages[holding] = {
            statement: report(
                statement,
                holding,
                from_date,
                to_date,
                finance_book=adjustment_book,
                include_default_book_entries=True,
            )
            for statement in ("balance_sheet", "profit_and_loss")
        }
        native_packages[holding]["cash_flow"] = statutory_cash_flow(
            holding,
            from_date,
            to_date,
            finance_book=adjustment_book,
            comparative_from_date=comparative_from_date,
            comparative_to_date=comparative_to_date,
            _require_comparative=False,
            include_default_book_entries=True,
        )
        result["consolidated_after_native_adjustment"] = {
            statement: _aggregate_statement(
                statement,
                native_packages,
                companies,
                from_date,
                to_date,
            )
            for statement in ("balance_sheet", "profit_and_loss")
        }
        result["consolidated_after_native_adjustment"]["cash_flow"] = _aggregate_cash_flow(
            native_packages,
            companies,
            from_date,
            to_date,
            comparative_from_date=comparative_from_date,
            comparative_to_date=comparative_to_date,
        )
        result["native_adjustment_readback"] = {
            "finance_book": adjustment_book,
            "holding_company": holding,
            "status": "derived_from_native_gl",
        }
        if comparative_from_date and comparative_to_date:
            native_comparative = {
                company: packages[company]["comparative"]
                for company in companies
            }
            native_comparative[holding] = {
                statement: report(
                    statement,
                    holding,
                    comparative_from_date,
                    comparative_to_date,
                    finance_book=adjustment_book,
                    include_default_book_entries=True,
                )
                for statement in ("balance_sheet", "profit_and_loss")
            }
            result["consolidated_after_native_adjustment_comparative"] = {
                statement: _aggregate_statement(
                    statement,
                    native_comparative,
                    companies,
                    comparative_from_date,
                    comparative_to_date,
                )
                for statement in ("balance_sheet", "profit_and_loss")
            }
            native_comparative_cash_flow = {
                company: {
                    **packages[company]["cash_flow"],
                    "lines": [
                        {
                            **line,
                            "amount": line.get("comparative_amount"),
                            "status": line.get("comparative_status"),
                            "comparative_amount": None,
                            "comparative_status": "not_requested",
                        }
                        for line in packages[company]["cash_flow"].get("lines", [])
                    ],
                }
                for company in companies
            }
            native_comparative_cash_flow[holding] = statutory_cash_flow(
                holding,
                comparative_from_date,
                comparative_to_date,
                finance_book=adjustment_book,
                _require_comparative=False,
                include_default_book_entries=True,
            )
            result["consolidated_after_native_adjustment_comparative"]["cash_flow"] = (
                _aggregate_cash_flow(
                    {company: {"cash_flow": native_comparative_cash_flow[company]} for company in companies},
                    companies,
                    comparative_from_date,
                    comparative_to_date,
                )
            )
    return result


def create_consolidation_adjustment(companies: list[str], from_date: str, to_date: str, posting_date: str, run_id: str) -> dict[str, Any]:
    """Create one idempotent draft native JE in Letron Holding."""
    frappe = _frappe()
    settings = _consolidation_settings()
    companies = _configured_companies(companies)
    holding = str(settings.get("holding_company") or "")
    finance_book = str(settings.get("finance_book") or "")
    if not holding or not finance_book or holding not in companies:
        frappe.throw("Consolidation policy must include the holding company and finance book", exc=frappe.ValidationError)
    if not run_id or not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", run_id):
        frappe.throw("run_id is invalid", exc=frappe.ValidationError)
    if from_date > to_date or posting_date < from_date or posting_date > to_date:
        frappe.throw("posting_date and the reporting range must be ordered", exc=frappe.ValidationError)
    marker = f"LETRON-CONSOLIDATION|run={run_id}|from={from_date}|to={to_date}"
    existing = frappe.db.get_value("Journal Entry", {"company": holding, "finance_book": finance_book, "user_remark": ["like", f"%{marker}%"]}, "name")
    if existing:
        return {"ok": True, "idempotent": True, "journal_entry": existing, "status": frappe.db.get_value("Journal Entry", existing, "docstatus")}
    schedule = elimination_schedule(companies, from_date, to_date)
    if not schedule:
        return {"ok": True, "idempotent": False, "journal_entry": None, "status": "no_adjustments", "elimination_schedule": []}
    if settings.get("require_closed_period", False):
        open_companies = [
            company
            for company in companies
            if not frappe.db.exists(
                "Period Closing Voucher",
                {
                    "company": company,
                    "docstatus": 1,
                    "period_end_date": [">=", to_date],
                },
            )
        ]
        if open_companies:
            frappe.throw(
                "Consolidation requires a submitted Period Closing Voucher through "
                f"{to_date} for: {', '.join(open_companies)}",
                exc=frappe.ValidationError,
            )
    cost_center = _consolidation_cost_center(holding)
    if not cost_center:
        frappe.throw(f"Missing consolidation Cost Center for {holding}", exc=frappe.ValidationError)
    accounts = []
    for row in schedule:
        debit = frappe.db.get_value(
            "Account",
            {"company": holding, "account_number": row["debit_account_code"]},
            "name",
        )
        credit = frappe.db.get_value(
            "Account",
            {"company": holding, "account_number": row["credit_account_code"]},
            "name",
        )
        if not debit or not credit:
            frappe.throw(f"Consolidation account is not materialized for {holding}: {row['debit_account_code']}/{row['credit_account_code']}", exc=frappe.ValidationError)
        accounts.extend([
            {"account": debit, "debit_in_account_currency": row["amount"], "debit": row["amount"], "cost_center": cost_center},
            {"account": credit, "credit_in_account_currency": row["amount"], "credit": row["amount"], "cost_center": cost_center},
        ])
    doc = frappe.get_doc({"doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": holding, "posting_date": posting_date, "finance_book": finance_book, "user_remark": marker, "remark": marker, "party_not_required": 1, "accounts": accounts})
    doc.insert(ignore_permissions=True)
    return {"ok": True, "idempotent": False, "journal_entry": doc.name, "status": doc.docstatus, "finance_book": finance_book, "elimination_schedule": schedule}


def submit_consolidation_adjustment(journal_entry: str) -> dict[str, Any]:
    frappe = _frappe()
    settings = _consolidation_settings()
    doc = frappe.get_doc("Journal Entry", journal_entry)
    doc.check_permission("submit")
    if not str(doc.user_remark or "").startswith("LETRON-CONSOLIDATION|"):
        frappe.throw("Only policy-created consolidation Journal Entries may be submitted", exc=frappe.PermissionError)
    if doc.company != settings.get("holding_company") or doc.finance_book != settings.get("finance_book"):
        frappe.throw("Consolidation Journal Entry must belong to the policy holding Company and Finance Book", exc=frappe.PermissionError)
    doc.submit()
    return {"ok": True, "journal_entry": doc.name, "status": doc.docstatus}


def cancel_consolidation_adjustment(journal_entry: str) -> dict[str, Any]:
    frappe = _frappe()
    settings = _consolidation_settings()
    doc = frappe.get_doc("Journal Entry", journal_entry)
    doc.check_permission("cancel")
    if not str(doc.user_remark or "").startswith("LETRON-CONSOLIDATION|"):
        frappe.throw("Only policy-created consolidation Journal Entries may be cancelled", exc=frappe.PermissionError)
    if doc.company != settings.get("holding_company") or doc.finance_book != settings.get("finance_book"):
        frappe.throw("Consolidation Journal Entry must belong to the policy holding Company and Finance Book", exc=frappe.PermissionError)
    doc.cancel()
    return {"ok": True, "journal_entry": doc.name, "status": doc.docstatus}


def _mapping_version() -> int:
    from letron_api.control.policy import load_policy

    return int(load_policy()["shared"]["coa_template"].get("bctc_mapping", {}).get("version", 1))


def _statutory_form(form_code: str) -> dict[str, Any]:
    """Return one policy-owned TT99 statutory form definition."""
    from letron_api.control.policy import load_policy

    mapping = load_policy()["shared"]["coa_template"].get("bctc_mapping", {})
    statutory_forms = mapping.get("statutory_forms", {})
    forms = statutory_forms.get("forms", {}) if isinstance(statutory_forms, dict) else {}
    form = forms.get(form_code) if isinstance(forms, dict) else None
    if not isinstance(form, dict):
        raise TypeError(f"Unsupported statutory form: {form_code}")
    return form


def _calculate_statutory_lines(
    form: dict[str, Any],
    balances: dict[str, float],
    metric_values: dict[str, float] | None = None,
    classified_values: dict[str, float | None] | None = None,
    not_applicable_metrics: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Calculate policy form lines and fail closed on missing classification data.

    Native GL account balances do not carry the maturity and subledger split
    needed by several TT99 rows. Those rows are deliberately returned with a
    null amount until the required native detail is available; they are never
    guessed from an aggregate account balance.
    """
    values: dict[str, float | None] = {}
    unresolved: list[str] = []
    result: list[dict[str, Any]] = []
    formula_token = re.compile(r"[0-9]+[a-z]?")
    metric_values = metric_values or {}
    classified_values = classified_values or {}
    not_applicable_metrics = not_applicable_metrics or set()

    line_status: dict[str, str] = {}
    # Resolve account rows first, then repeatedly resolve formulas. This keeps
    # the policy free to list a statutory subtotal before its child rows, as
    # the official form does, without relying on YAML ordering.
    for line in form["lines"]:
        if line["line_type"] != "account":
            continue
        code = str(line["code"])
        source = line.get("source")
        if source == "consolidation_only":
            values[code] = None
            line_status[code] = "not_applicable"
        elif line.get("maturity") or source == "subledger_classification_required":
            classified_value = classified_values.get(code)
            if classified_value is not None:
                values[code] = float(classified_value)
                line_status[code] = "derived"
            elif abs(_mapped_amount(balances, line["source_account_codes"])) <= 0.0005:
                values[code] = 0.0
                line_status[code] = "not_applicable"
            else:
                values[code] = None
                line_status[code] = "requires_classification"
        elif not line.get("source_account_codes"):
            values[code] = None
            line_status[code] = "not_applicable"
        else:
            values[code] = _mapped_amount(balances, line["source_account_codes"])
            line_status[code] = "derived"

    for line in form["lines"]:
        if line["line_type"] != "metric":
            continue
        code = str(line["code"])
        metric = str(line.get("metric") or "")
        if metric in metric_values and metric_values[metric] is not None:
            values[code] = float(metric_values[metric])
            line_status[code] = "derived"
        elif metric in not_applicable_metrics:
            values[code] = None
            line_status[code] = "not_applicable"
        else:
            values[code] = None
            line_status[code] = "requires_metric"

    pending = [line for line in form["lines"] if line["line_type"] == "subtotal"]
    while pending:
        progressed = False
        remaining = []
        for line in pending:
            code = str(line["code"])
            references = formula_token.findall(str(line["formula"]))
            if not all(reference in values and values[reference] is not None for reference in references):
                remaining.append(line)
                continue
            pieces = re.split(r"([+-])", str(line["formula"]))
            first_value = values.get(pieces[0])
            if first_value is None:
                remaining.append(line)
                continue
            amount = float(first_value)
            for operator, reference in zip(pieces[1::2], pieces[2::2]):
                reference_value = values.get(reference)
                if reference_value is None:
                    remaining.append(line)
                    break
                value = float(reference_value)
                amount = amount + value if operator == "+" else amount - value
            else:
                values[code] = amount
                line_status[code] = "derived"
                progressed = True
                continue
        if not progressed:
            for line in remaining:
                values[str(line["code"])] = None
                references = formula_token.findall(str(line["formula"]))
                line_status[str(line["code"])] = (
                    "requires_metric"
                    if any(line_status.get(reference) == "requires_metric" for reference in references)
                    else "requires_classification"
                )
            break
        pending = remaining

    for line in form["lines"]:
        code = str(line["code"])
        line_type = str(line["line_type"])
        status = line_status.get(code, "requires_metric")
        amount = values.get(code)
        if status not in {"derived", "not_applicable"}:
            unresolved.append(code)
        result.append(
            {
                "code": code,
                "name": line["name"],
                "line_type": line_type,
                "amount": round(amount, 2) if amount is not None else None,
                "status": status,
            }
        )

    return result, unresolved


def statutory_cash_flow(
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    comparative_from_date: str | None = None,
    comparative_to_date: str | None = None,
    _require_comparative: bool = True,
    include_default_book_entries: bool = False,
    _metric_marker: str | None = None,
) -> dict[str, Any]:
    """Expose TT99 B03-DN using native Cash Flow and fail-closed metrics."""
    frappe = _frappe()
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Unknown Company: {company}", exc=frappe.DoesNotExistError)
    if from_date > to_date:
        frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
    if (comparative_from_date is None) != (comparative_to_date is None):
        frappe.throw(
            "comparative_from_date and comparative_to_date must be provided together",
            exc=frappe.ValidationError,
        )
    if comparative_from_date and comparative_to_date and comparative_from_date > comparative_to_date:
        frappe.throw(
            "comparative_from_date must not be after comparative_to_date",
            exc=frappe.ValidationError,
        )

    form = _statutory_form("B03-DN")
    current = _cash_flow_metrics(
        company,
        from_date,
        to_date,
        finance_book,
        include_default_book_entries=include_default_book_entries,
        _metric_marker=_metric_marker,
    )
    _validate_accounting_currency(str(current["currency"]))
    lines, unresolved = _calculate_statutory_lines(
        form, {}, metric_values=current["metrics"]
    )
    periods: dict[str, Any] = {
        "current": {"from_date": from_date, "to_date": to_date, "status": "derived"}
    }
    comparative: dict[str, Any] | None = None
    if comparative_from_date and comparative_to_date:
        comparative = _cash_flow_metrics(
            company,
            comparative_from_date,
            comparative_to_date,
            finance_book,
            include_default_book_entries=include_default_book_entries,
            _metric_marker=_metric_marker,
        )
        _validate_accounting_currency(str(comparative["currency"]))
        comparative_lines, comparative_unresolved = _calculate_statutory_lines(
            form, {}, metric_values=comparative["metrics"]
        )
        for line, comparative_line in zip(lines, comparative_lines, strict=True):
            line["comparative_amount"] = comparative_line["amount"]
            line["comparative_status"] = comparative_line["status"]
            line["values"] = {
                "current_period": line["amount"],
                "comparative_period": comparative_line["amount"],
            }
        unresolved = sorted(set(unresolved) | set(comparative_unresolved))
        periods["comparative"] = {
            "from_date": comparative_from_date,
            "to_date": comparative_to_date,
            "status": "derived",
        }
    else:
        for line in lines:
            line["comparative_amount"] = None
            line["comparative_status"] = (
                "requires_comparative_period" if _require_comparative else "not_requested"
            )
            line["values"] = {
                "current_period": line["amount"],
                "comparative_period": None,
            }
        if _require_comparative:
            unresolved = sorted(set(unresolved) | {str(line["code"]) for line in lines})
        periods["comparative"] = {
            "from_date": None,
            "to_date": None,
            "status": "requires_comparative_period" if _require_comparative else "not_requested",
        }

    unmapped = sorted(
        set(current.get("unmapped_account_codes", []))
        | set(comparative.get("unmapped_account_codes", []) if comparative else [])
    )
    cash_flow_exceptions = list(current.get("cash_flow_exceptions", []))
    if comparative:
        cash_flow_exceptions.extend(comparative.get("cash_flow_exceptions", []))
    return {
        "ok": not unresolved and not unmapped and not cash_flow_exceptions,
        "form_code": "B03-DN",
        "form_name": form["name"],
        "statement": form["statement"],
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "finance_book": finance_book,
        "currency": current["currency"],
        "mapping_version": _mapping_version(),
        "columns": form["columns"],
        "periods": periods,
        "lines": lines,
        "unresolved_line_codes": unresolved,
        "unmapped_account_codes": unmapped,
        "native_source": "erpnext_cash_flow_and_gl_entry",
        "native_metrics": current["metrics"],
        "native_cash_flow": current["native"],
        "native_comparative_cash_flow": comparative["native"] if comparative else None,
        "cash_flow_events": current.get("cash_flow_events", []),
        "cash_flow_exceptions": cash_flow_exceptions,
    }


def statutory_report(
    form_code: str,
    company: str,
    from_date: str,
    to_date: str,
    finance_book: str | None = None,
    comparative_from_date: str | None = None,
    comparative_to_date: str | None = None,
) -> dict[str, Any]:
    """Expose a TT99 form from native GL data without writing ledger entries."""
    frappe = _frappe()
    if not frappe.db.exists("Company", company):
        frappe.throw(f"Unknown Company: {company}", exc=frappe.DoesNotExistError)
    if from_date > to_date:
        frappe.throw("from_date must not be after to_date", exc=frappe.ValidationError)
    form = _statutory_form(form_code)
    if form_code == "B09-DN":
        return b09_report(
            company=company,
            from_date=from_date,
            to_date=to_date,
            finance_book=finance_book,
            comparative_from_date=comparative_from_date,
            comparative_to_date=comparative_to_date,
        )
    if form_code == "B03-DN":
        return statutory_cash_flow(
            company=company,
            from_date=from_date,
            to_date=to_date,
            finance_book=finance_book,
            comparative_from_date=comparative_from_date,
            comparative_to_date=comparative_to_date,
        )
    balances, native_metadata = _native_account_balances(
        str(form["statement"]), company, from_date, to_date, finance_book
    )
    _validate_accounting_currency(str(native_metadata["currency"]))
    if form_code == "B02-DN":
        lines, unresolved = _calculate_b02_period(
            form, company, from_date, to_date, balances, finance_book
        )
    else:
        classified_values = _native_statutory_detail_values(
            form_code,
            form,
            company,
            from_date,
            to_date,
            balances,
            finance_book=finance_book,
            as_of_date=to_date,
        )
        lines, unresolved = _calculate_statutory_lines(
            form, balances, classified_values=classified_values
        )
    periods: dict[str, Any] = {
        "current": {
            "from_date": from_date,
            "to_date": to_date,
            "status": "derived",
        }
    }

    if form_code == "B01-DN":
        opening_balances = native_metadata.get("opening_balances", {})
        opening_as_of = (date.fromisoformat(from_date) - timedelta(days=1)).isoformat()
        opening_classified_values = _native_statutory_detail_values(
            form_code,
            form,
            company,
            from_date,
            opening_as_of,
            opening_balances if isinstance(opening_balances, dict) else {},
            finance_book=finance_book,
            as_of_date=opening_as_of,
        )
        opening_lines, opening_unresolved = _calculate_statutory_lines(
            form,
            opening_balances if isinstance(opening_balances, dict) else {},
            classified_values=opening_classified_values,
        )
        for line, opening_line in zip(lines, opening_lines, strict=True):
            line["opening_amount"] = opening_line["amount"]
            line["opening_status"] = opening_line["status"]
            line["values"] = {
                "closing_balance": line["amount"],
                "opening_balance": opening_line["amount"],
            }
        unresolved = sorted(set(unresolved) | set(opening_unresolved))
        periods["opening"] = {
            "from_date": None,
            "to_date": None,
            "status": "derived_from_native_opening_balance",
        }
    elif form_code == "B02-DN":
        if (comparative_from_date is None) != (comparative_to_date is None):
            frappe.throw(
                "comparative_from_date and comparative_to_date must be provided together",
                exc=frappe.ValidationError,
            )
        if comparative_from_date and comparative_to_date:
            if comparative_from_date > comparative_to_date:
                frappe.throw(
                    "comparative_from_date must not be after comparative_to_date",
                    exc=frappe.ValidationError,
                )
            comparative_balances, comparative_metadata = _native_account_balances(
                str(form["statement"]),
                company,
                comparative_from_date,
                comparative_to_date,
                finance_book,
            )
            _validate_accounting_currency(str(comparative_metadata["currency"]))
            comparative_lines, comparative_unresolved = _calculate_b02_period(
                form,
                company,
                comparative_from_date,
                comparative_to_date,
                comparative_balances,
                finance_book,
            )
            for line, comparative_line in zip(lines, comparative_lines, strict=True):
                line["comparative_amount"] = comparative_line["amount"]
                line["comparative_status"] = comparative_line["status"]
                line["values"] = {
                    "current_period": line["amount"],
                    "comparative_period": comparative_line["amount"],
                }
            unresolved = sorted(set(unresolved) | set(comparative_unresolved))
            periods["comparative"] = {
                "from_date": comparative_from_date,
                "to_date": comparative_to_date,
                "status": "derived",
            }
        else:
            for line in lines:
                line["comparative_amount"] = None
                line["comparative_status"] = "requires_comparative_period"
                line["values"] = {
                    "current_period": line["amount"],
                    "comparative_period": None,
                }
            unresolved = sorted(
                set(unresolved) | {str(line["code"]) for line in lines}
            )
            periods["comparative"] = {
                "from_date": None,
                "to_date": None,
                "status": "requires_comparative_period",
            }
    mapped_codes = {
        str(code)
        for line in form["lines"]
        for code in line.get("source_account_codes", [])
    }
    unmapped = sorted(
        code
        for code, amount in balances.items()
        if abs(amount) > 0.0005 and not _mapped(code, mapped_codes)
    )
    return {
        "ok": not unresolved and not unmapped,
        "form_code": form_code,
        "form_name": form["name"],
        "statement": form["statement"],
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "finance_book": finance_book,
        "currency": native_metadata["currency"],
        "mapping_version": _mapping_version(),
        "columns": form["columns"],
        "periods": periods,
        "lines": lines,
        "unresolved_line_codes": unresolved,
        "unmapped_account_codes": unmapped,
        "native_source": "erpnext_gl_entry",
    }
