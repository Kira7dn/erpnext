import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import yaml
from letron_api.control.holding_finance import _expected_tax_account_code, _parent_code
from letron_api.control.policy import _account_reference
from letron_api.finance import vas_reports
from letron_api.finance.vas_reports import (
    _aggregate_cash_flow,
    _aggregate_statement,
    _apply_elimination_schedule,
    _calculate_statutory_lines,
    _cash_flow_policy,
    _compile_intercompany_marker,
    _is_balanced_intercompany_match,
    _mapped_abs_amount,
    _mapped_amount,
    _note_snapshot,
    _native_cash_flow_events,
    _parse_intercompany_marker,
    _render_intercompany_marker,
    elimination_schedule,
)

POLICY = yaml.safe_load(
    (Path(__file__).parents[2] / "config" / "policy.yaml").read_text(encoding="utf-8")
)
COA = POLICY["shared"]["coa_template"]["accounts"]
ACCOUNT_TYPES = POLICY["shared"]["coa_template"]["account_types"]
BCTC = POLICY["shared"]["coa_template"]["bctc_mapping"]
COA_TEMPLATE = POLICY["shared"]["coa_template"]
FISCAL_YEAR = POLICY["shared"]["fiscal_year"]


def test_vas_coa_uses_unique_direct_account_codes() -> None:
    codes = [item["code"] for item in COA]

    assert len(codes) == len(set(codes))
    assert {item["code"] for item in COA} >= {
        "111", "112", "131", "1331", "211", "214", "241", "331", "3331",
        "411", "421", "511", "632", "642", "711", "811", "821", "911",
    }


def test_native_cash_flow_events_use_cash_sign_and_direction_specific_rules(monkeypatch) -> None:
    class FakeFrappe:
        @staticmethod
        def get_all(doctype, **kwargs):
            if doctype == "Account":
                return [
                    {"name": "Cash - L", "account_number": "111"},
                    {"name": "Interest - L", "account_number": "635"},
                    {"name": "Fixed Asset - L", "account_number": "211"},
                    {"name": "Unclassified - L", "account_number": "9999"},
                ]
            return [
                {"name": "GL-1", "voucher_type": "Payment Entry", "voucher_no": "PE-1", "account": "Cash - L", "debit": 0, "credit": 100},
                {"name": "GL-2", "voucher_type": "Payment Entry", "voucher_no": "PE-1", "account": "Interest - L", "debit": 100, "credit": 0},
                {"name": "GL-3", "voucher_type": "Journal Entry", "voucher_no": "JV-1", "account": "Cash - L", "debit": 250, "credit": 0},
                {"name": "GL-4", "voucher_type": "Journal Entry", "voucher_no": "JV-1", "account": "Fixed Asset - L", "debit": 0, "credit": 250},
                {"name": "GL-5", "voucher_type": "Journal Entry", "voucher_no": "JV-2", "account": "Cash - L", "debit": 0, "credit": 10},
                {"name": "GL-6", "voucher_type": "Journal Entry", "voucher_no": "JV-2", "account": "Unclassified - L", "debit": 10, "credit": 0},
            ]

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())

    metrics, events = _native_cash_flow_events("LeSC", "2026-01-01", "2026-12-31")

    assert metrics["interest_paid"] == -100
    assert metrics["fixed_asset_disposals"] == 250
    assert not metrics.get("fixed_asset_purchases")
    assert any(event["status"] == "requires_classification" for event in events)


def test_special_vas_accounts_use_native_erpnext_account_types() -> None:
    assert ACCOUNT_TYPES["111"] == "Cash"
    assert ACCOUNT_TYPES["112"] == "Bank"
    assert ACCOUNT_TYPES["131"] == "Receivable"
    assert ACCOUNT_TYPES["1331"] == "Tax"
    assert ACCOUNT_TYPES["33311"] == "Tax"
    assert ACCOUNT_TYPES["2141"] == "Accumulated Depreciation"
    assert ACCOUNT_TYPES["2147"] == "Accumulated Depreciation"
    assert ACCOUNT_TYPES["2411"] == "Capital Work in Progress"
    assert ACCOUNT_TYPES["6424"] == "Depreciation"


def test_tax_templates_use_separate_input_and_output_accounts() -> None:
    assert _expected_tax_account_code("Purchase Taxes and Charges Template") == "1331"
    assert _expected_tax_account_code("Sales Taxes and Charges Template") == "33311"
    assert _expected_tax_account_code("Item Tax Template") == "33311"


def test_vas_bctc_mapping_covers_core_statements() -> None:
    statements = BCTC["statements"]
    assert {"balance_sheet", "profit_and_loss"} <= set(statements)
    mapped = {code for lines in statements.values() for line in lines for code in line["account_codes"]}
    assert all(any(code == candidate or code.startswith(candidate) for candidate in mapped) for code in {item["code"] for item in COA})
    assert len(COA) >= 150


def test_statutory_calculator_evaluates_subtotals_without_writing_gl() -> None:
    form = BCTC["statutory_forms"]["forms"]["B02-DN"]
    lines, unresolved = _calculate_statutory_lines(
        form,
        {"511": 1000, "521": 100, "632": 400, "515": 50, "635": 20, "641": 30, "642": 40, "711": 10, "811": 5, "82111": 50, "8212": 0},
    )

    values = {line["code"]: line["amount"] for line in lines}
    assert values["10"] == 900
    assert values["20"] == 500
    assert values["40"] == 5
    assert "21" in unresolved
    assert "24" in unresolved


def test_statutory_calculator_fails_closed_for_current_non_current_split() -> None:
    form = BCTC["statutory_forms"]["forms"]["B01-DN"]
    lines, unresolved = _calculate_statutory_lines(form, {"131": 100, "331": -80})

    assert next(line for line in lines if line["code"] == "130")["status"] == "requires_classification"
    assert next(line for line in lines if line["code"] == "210")["status"] == "requires_classification"
    assert {"130", "210", "310", "330"} <= set(unresolved)
    assert next(line for line in lines if line["code"] == "123")["status"] == "not_applicable"


def test_statutory_calculator_resolves_native_metrics_and_subtotals() -> None:
    form = BCTC["statutory_forms"]["forms"]["B03-DN"]
    lines, unresolved = _calculate_statutory_lines(
        form,
        {},
        metric_values={
            "profit_before_tax": 500,
            "depreciation": 10,
            "receivables_change": -20,
            "inventory_change": 5,
        },
    )

    values = {line["code"]: line["amount"] for line in lines}
    assert values["01"] == 500
    assert values["02"] == 10
    assert values["08"] is None
    assert "08" in unresolved


def test_native_statutory_detail_values_classifies_maturity_and_markers(monkeypatch) -> None:
    form = BCTC["statutory_forms"]["forms"]["B01-DN"]

    class FakeFrappe:
        @staticmethod
        def get_all(doctype, **kwargs):
            if doctype == "Account":
                return [
                    {"name": "131 - Receivable", "account_number": "131"},
                    {"name": "1281 - Investment", "account_number": "1281"},
                ]
            if kwargs["filters"].get("remarks"):
                return [
                    {
                        "account": "1281 - Investment",
                        "debit": 20,
                        "credit": 0,
                    }
                ]
            return [
                {
                    "account": "131 - Receivable",
                    "debit": 100,
                    "credit": 0,
                    "due_date": "2027-01-01",
                }
            ]

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    values = vas_reports._native_statutory_detail_values(
        "B01-DN",
        form,
        "LeSC",
        "2026-01-01",
        "2026-12-31",
        {"131": 100, "1281": 20},
        as_of_date="2026-12-31",
    )

    assert values["131"] == 100
    assert values["211"] == 0
    assert values["112"] == 20


def test_native_eps_uses_native_company_shareholder_balance(monkeypatch) -> None:
    class FakeFrappe:
        @staticmethod
        def get_all(doctype, **kwargs):
            assert doctype == "Shareholder"
            assert kwargs["filters"] == {"company": "LeSC", "is_company": 1}
            return ["LeSC-Shareholder"]

        @staticmethod
        def get_doc(doctype, name):
            assert (doctype, name) == ("Shareholder", "LeSC-Shareholder")
            return SimpleNamespace(
                share_balance=[{"no_of_shares": 250}, {"no_of_shares": 250}]
            )

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    metrics, not_applicable = vas_reports._native_eps_metrics(
        "LeSC", "2026-01-01", "2026-12-31", 1000
    )

    assert metrics == {"basic_eps": 2.0}
    assert not_applicable == {"diluted_eps"}


def test_b02_period_derives_eps_and_marks_diluted_eps_not_applicable(monkeypatch) -> None:
    form = BCTC["statutory_forms"]["forms"]["B02-DN"]
    monkeypatch.setattr(
        vas_reports,
        "_native_statutory_detail_values",
        lambda *args, **kwargs: {"21": 10.0, "24": 20.0},
    )
    monkeypatch.setattr(
        vas_reports,
        "_native_eps_metrics",
        lambda *args, **kwargs: ({"basic_eps": 2.5}, {"diluted_eps"}),
    )

    lines, unresolved = vas_reports._calculate_b02_period(
        form,
        "LeSC",
        "2026-01-01",
        "2026-12-31",
        {
            "511": 1000,
            "521": 100,
            "632": 400,
            "515": 50,
            "635": 20,
            "641": 30,
            "642": 40,
            "711": 10,
            "811": 5,
            "82111": 50,
            "8212": 0,
        },
    )

    result = {line["code"]: line for line in lines}
    assert unresolved == []
    assert result["60"]["amount"] == 425.0
    assert result["70"] == {
        "code": "70",
        "name": "Lãi cơ bản trên cổ phiếu",
        "line_type": "metric",
        "amount": 2.5,
        "status": "derived",
    }
    assert result["71"]["status"] == "not_applicable"


def test_b03_report_uses_native_metrics_and_requires_unavailable_detail(monkeypatch) -> None:
    class FakeDB:
        @staticmethod
        def exists(doctype, name_or_filters):
            if doctype == "Company":
                return name_or_filters == "LeSC"
            return doctype == "Fiscal Year Company"

        @staticmethod
        def get_value(doctype, filters, fieldname):
            assert doctype == "Fiscal Year"
            return "2026"

    class FakeFrappe:
        db = FakeDB()
        ValidationError = ValueError
        DoesNotExistError = LookupError

        @staticmethod
        def get_cached_value(doctype, name, fieldname):
            assert (doctype, name, fieldname) == ("Company", "LeSC", "default_currency")
            return "VND"

        @staticmethod
        def throw(message, exc=ValueError):
            raise exc(message)

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    monkeypatch.setattr(vas_reports, "_validate_accounting_currency", lambda currency: None)
    monkeypatch.setattr(vas_reports, "_mapping_version", lambda: 1)
    monkeypatch.setattr(
        vas_reports,
        "native_cash_flow",
        lambda *args, **kwargs: {"columns": [], "result": []},
    )
    monkeypatch.setattr(
        vas_reports,
        "report",
        lambda *args, **kwargs: {
            "lines": [
                {"code": "E1", "amount": 1000},
                {"code": "E2", "amount": 0},
                {"code": "E3", "amount": 100},
                {"code": "E4", "amount": 200},
                {"code": "E5", "amount": 100},
                {"code": "E6", "amount": 50},
                {"code": "E7", "amount": 100},
                {"code": "E8", "amount": 50},
                {"code": "E9", "amount": 25},
                {"code": "E10", "amount": 25},
            ],
            "unmapped_account_codes": [],
        },
    )
    monkeypatch.setattr(
        vas_reports,
        "_native_cash_flow_account_type_change",
        lambda company, from_date, to_date, account_type, finance_book=None, include_default_book_entries=False: {
            "Depreciation": 10,
            "Receivable": -20,
            "Stock": 5,
        }.get(account_type, 0),
    )
    monkeypatch.setattr(
        vas_reports,
        "_native_account_balances",
        lambda *args, **kwargs: (
            {"111": 100},
            {"currency": "VND", "opening_balances": {"111": 40}},
        ),
    )

    result = vas_reports.statutory_cash_flow(
        "LeSC",
        "2026-01-01",
        "2026-12-31",
        comparative_from_date="2025-01-01",
        comparative_to_date="2025-12-31",
    )

    lines = {line["code"]: line for line in result["lines"]}
    assert lines["01"]["amount"] == 600
    assert lines["02"]["amount"] == 10
    assert lines["09"]["amount"] == -20
    assert lines["10"]["amount"] == 5
    assert lines["60"]["amount"] == 40
    assert lines["03"]["status"] == "requires_metric"
    assert lines["08"]["status"] == "requires_metric"
    assert result["ok"] is False


def test_b01_report_exposes_native_opening_balance(monkeypatch) -> None:
    class FakeDB:
        @staticmethod
        def exists(doctype, name):
            return doctype == "Company" and name == "LeSC"

    class FakeFrappe:
        db = FakeDB()
        ValidationError = ValueError
        DoesNotExistError = LookupError

        @staticmethod
        def throw(message, exc=ValueError):
            raise exc(message)

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    monkeypatch.setattr(vas_reports, "_validate_accounting_currency", lambda currency: None)
    monkeypatch.setattr(vas_reports, "_mapping_version", lambda: 1)
    monkeypatch.setattr(
        vas_reports,
        "_native_account_balances",
        lambda *args, **kwargs: (
            {"111": 100.0},
            {"currency": "VND", "opening_balances": {"111": 40.0}},
        ),
    )

    result = vas_reports.statutory_report(
        "B01-DN", "LeSC", "2026-01-01", "2026-12-31"
    )
    line = next(item for item in result["lines"] if item["code"] == "111")

    assert line["amount"] == 100.0
    assert line["opening_amount"] == 40.0
    assert line["values"] == {"closing_balance": 100.0, "opening_balance": 40.0}
    assert result["periods"]["opening"]["status"] == "derived_from_native_opening_balance"


def test_b02_report_requires_explicit_comparative_period(monkeypatch) -> None:
    class FakeDB:
        @staticmethod
        def exists(doctype, name):
            return doctype == "Company" and name == "LeSC"

    class FakeFrappe:
        db = FakeDB()
        ValidationError = ValueError
        DoesNotExistError = LookupError

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    monkeypatch.setattr(vas_reports, "_validate_accounting_currency", lambda currency: None)
    monkeypatch.setattr(vas_reports, "_mapping_version", lambda: 1)
    monkeypatch.setattr(
        vas_reports,
        "_native_account_balances",
        lambda *args, **kwargs: ({"511": 100.0}, {"currency": "VND"}),
    )

    result = vas_reports.statutory_report(
        "B02-DN", "LeSC", "2026-01-01", "2026-12-31"
    )
    line = next(item for item in result["lines"] if item["code"] == "01")

    assert result["ok"] is False
    assert result["periods"]["comparative"]["status"] == "requires_comparative_period"
    assert line["comparative_amount"] is None
    assert line["comparative_status"] == "requires_comparative_period"


def test_native_finance_book_readback_does_not_double_count_blank_book_rows(
    monkeypatch,
) -> None:
    calls = []

    class FakeDB:
        @staticmethod
        def exists(doctype, filters):
            assert doctype == "Fiscal Year Company"
            assert filters == {"parent": "2026", "company": "Letron Holding"}
            return True

    class FakeFrappe:
        db = FakeDB()
        ValidationError = ValueError

        @staticmethod
        def get_all(doctype, **kwargs):
            assert doctype == "Fiscal Year"
            return ["2026"]

        @staticmethod
        def get_cached_value(doctype, company, field):
            assert (doctype, company, field) == (
                "Company",
                "Letron Holding",
                "default_finance_book",
            )
            return "Default Book"

    def fake_native_once(statement, company, from_date, to_date, finance_book=None, **kwargs):
        calls.append(finance_book)
        values = {
            "Default Book": ({"111": 100.0}, {"111": 10.0}),
            "Consolidation Adjustment": ({"111": 5.0, "112": 7.0}, {"111": 1.0}),
            "": ({"111": 2.0}, {"111": 0.5}),
        }
        balances, opening = values[finance_book]
        return balances, {"currency": "VND", "opening_balances": opening}

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    monkeypatch.setattr(vas_reports, "_native_account_balances_once", fake_native_once)

    balances, metadata = vas_reports._native_account_balances(
        "balance_sheet",
        "Letron Holding",
        "2026-01-01",
        "2026-12-31",
        finance_book="Consolidation Adjustment",
        include_default_book_entries=True,
    )

    assert calls == ["Default Book", "Consolidation Adjustment", ""]
    assert balances == {"111": 103.0, "112": 7.0}
    assert metadata["opening_balances"] == {"111": 10.5}


def test_vas_mapping_rolls_up_native_leaf_accounts_into_parent_line() -> None:
    assert _mapped_amount(
        {"1331": 125.0, "1332": 25.0, "1388": 50.0, "6428": 300.0},
        ["133", "138"],
    ) == 200.0


def test_intercompany_elimination_rolls_up_leaf_account_codes() -> None:
    assert _mapped_abs_amount({"1311": 100.0, "1318": -25.0, "3318": 75.0}, ["131"]) == 125.0


def test_fiscal_year_is_declared_for_all_transaction_companies() -> None:
    assert FISCAL_YEAR["name"] == "2026"
    assert FISCAL_YEAR["start_date"] == "2026-01-01"
    assert FISCAL_YEAR["end_date"] == "2026-12-31"
    assert set(FISCAL_YEAR["companies"]) == {
        "Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"
    }


def test_fiscal_year_uses_calendar_year_boundary() -> None:
    fiscal_year = FISCAL_YEAR
    assert (fiscal_year["start_date"], fiscal_year["end_date"]) == (
        "2026-01-01",
        "2026-12-31",
    )


def test_coa_parent_is_the_longest_existing_account_code() -> None:
    codes = {"128", "1281", "1288", "13", "1331"}

    assert _parent_code({"code": "1281"}, codes) == "128"
    assert _parent_code({"code": "111"}, codes) is None
    assert _parent_code({"code": "1331", "parent_code": "13"}, codes) == "13"


def test_account_policy_reference_is_stable_by_code() -> None:
    assert _account_reference("account://33311") == "33311"
    assert _account_reference("33311 - Thuế GTGT đầu ra - LTVN") == "33311"
    assert _account_reference("Purchase") is None


def test_consolidation_policy_uses_holding_finance_book_and_native_codes() -> None:
    consolidation = POLICY["shared"]["consolidation"]
    assert consolidation["holding_company"] == "Letron Holding"
    assert consolidation["finance_book"] == "Consolidation Adjustment"
    assert set(consolidation["companies"]) == {
        "Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"
    }
    assert {rule["code"] for rule in consolidation["elimination_rules"]} == {
        "IC_AR_AP", "IC_REVENUE_COST"
    }
    finance_books = [
        entry
        for entry in POLICY["documents"]
        if entry["doctype"] == "Finance Book"
    ]
    assert finance_books == [{
        "doctype": "Finance Book",
        "name": "Consolidation Adjustment",
        "state": "present",
        "fields": {"finance_book_name": "Consolidation Adjustment"},
    }]


def test_intercompany_marker_is_compiled_from_policy_contract() -> None:
    pattern = _compile_intercompany_marker(POLICY["shared"]["consolidation"]["intercompany_marker"])
    assert _parse_intercompany_marker(
        "prefix LETRON-IC|id=IC-001|source=LeSM|counterparty=LeSC|type=service suffix",
        pattern,
    ) == {
        "matching_id": "IC-001",
        "source_company": "LeSM",
        "counterparty_company": "LeSC",
        "transaction_type": "service",
    }
    assert _parse_intercompany_marker("LETRON-IC|id=IC-001|counterparty=LeSC", pattern) is None


def test_intercompany_match_requires_two_directed_companies() -> None:
    rows = [
        {"company": "LeSC", "source_company": "LeSC", "counterparty_company": "LeSM", "transaction_type": "service"},
        {"company": "LeSM", "source_company": "LeSM", "counterparty_company": "LeSC", "transaction_type": "service"},
    ]
    item = {"companies": ["LeSC", "LeSM"], "counterparties": ["LeSC", "LeSM"], "rows": rows}
    assert _is_balanced_intercompany_match(item, ["Letron Holding", "LeSC", "LeSM"]) is True
    assert _is_balanced_intercompany_match({**item, "rows": rows[:1]}, ["Letron Holding", "LeSC", "LeSM"]) is False


def test_intercompany_match_rejects_asymmetric_native_gl_amounts() -> None:
    rows = [
        {"company": "LeSC", "source_company": "LeSC", "counterparty_company": "LeSM", "transaction_type": "service", "debit": 1000, "credit": 1000},
        {"company": "LeSM", "source_company": "LeSM", "counterparty_company": "LeSC", "transaction_type": "service", "debit": 500, "credit": 500},
    ]
    item = {"companies": ["LeSC", "LeSM"], "counterparties": ["LeSC", "LeSM"], "rows": rows}

    assert _is_balanced_intercompany_match(item, ["Letron Holding", "LeSC", "LeSM"]) is False


def test_intercompany_marker_supports_holding_name_and_policy_renderer() -> None:
    marker = _render_intercompany_marker("IC-001", "Letron Holding", "LeSM", "service")
    parsed = _parse_intercompany_marker(marker, _compile_intercompany_marker(POLICY["shared"]["consolidation"]["intercompany_marker"]))
    assert parsed == {
        "matching_id": "IC-001",
        "source_company": "Letron Holding",
        "counterparty_company": "LeSM",
        "transaction_type": "service",
    }


def test_elimination_schedule_preserves_actual_leaf_account_pairs(monkeypatch) -> None:
    companies = ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"]
    monkeypatch.setattr(
        vas_reports,
        "_consolidation_settings",
        lambda: {
            "companies": companies,
            "elimination_rules": [
                {
                    "code": "IC_AR_AP",
                    "source_account_codes": ["136"],
                    "counterparty_account_codes": ["336"],
                    "debit_account_code": "331",
                    "credit_account_code": "131",
                    "posting_mode": "mirror_actual_accounts",
                },
                {
                    "code": "IC_REVENUE_COST",
                    "source_account_codes": ["515"],
                    "counterparty_account_codes": ["635"],
                    "debit_account_code": "511",
                    "credit_account_code": "632",
                    "posting_mode": "mirror_actual_accounts",
                },
            ],
        },
    )
    monkeypatch.setattr(
        vas_reports,
        "intercompany_matches",
        lambda *args: [
            {
                "matching_id": "IC-LEAF-001",
                "companies": ["LeSC", "LeSM"],
                "counterparties": ["LeSC", "LeSM"],
                "transaction_type": "service",
                "balanced": True,
                "rows": [
                    {"account_code": "1368", "debit": 100, "credit": 0},
                    {"account_code": "3368", "debit": 0, "credit": 100},
                    {"account_code": "515", "debit": 0, "credit": 200},
                    {"account_code": "635", "debit": 200, "credit": 0},
                ],
            }
        ],
    )

    schedule = elimination_schedule(companies, "2026-01-01", "2026-12-31")

    assert {(row["debit_account_code"], row["credit_account_code"], row["amount"]) for row in schedule} == {
        ("3368", "1368", 100),
        ("635", "515", 200),
    }
    assert all("source_account_code" in row for row in schedule)


def test_intercompany_matching_uses_permission_aware_gl_query(monkeypatch) -> None:
    calls: list[str] = []

    class Row(dict):
        __getattr__ = dict.get

    class FakeDB:
        def get_value(self, doctype, account, field):
            assert doctype == "Account"
            return account

    class FakeFrappe:
        db = FakeDB()

        def get_list(self, doctype, **kwargs):
            calls.append("get_list")
            assert doctype == "GL Entry"
            assert kwargs["filters"]["company"] == ["in", ["LeSC", "LeSM"]]
            return [
                Row(
                    company="LeSC",
                    account="1368 - LeSC",
                    debit=100,
                    credit=0,
                    remarks="LETRON-IC|id=IC-001|source=LeSC|counterparty=LeSM|type=service",
                ),
                Row(
                    company="LeSC",
                    account="511 - LeSC",
                    debit=0,
                    credit=100,
                    remarks="LETRON-IC|id=IC-001|source=LeSC|counterparty=LeSM|type=service",
                ),
                Row(
                    company="LeSM",
                    account="3368 - LeSM",
                    debit=0,
                    credit=100,
                    remarks="LETRON-IC|id=IC-001|source=LeSM|counterparty=LeSC|type=service",
                ),
                Row(
                    company="LeSM",
                    account="632 - LeSM",
                    debit=100,
                    credit=0,
                    remarks="LETRON-IC|id=IC-001|source=LeSM|counterparty=LeSC|type=service",
                ),
            ]

    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())
    monkeypatch.setattr(
        vas_reports,
        "_consolidation_settings",
        lambda: {
            "intercompany_marker": "LETRON-IC|id={matching_id}|source={source_company}|counterparty={counterparty_company}|type={transaction_type}",
            "companies": ["LeSC", "LeSM"],
        },
    )

    result = vas_reports.intercompany_matches(
        ["LeSC", "LeSM"], "2026-01-01", "2026-12-31"
    )

    assert calls == ["get_list"]
    assert result[0]["balanced"] is True


def test_consolidation_aggregates_company_statements_without_writing_gl() -> None:
    reports = {
        company: {
            "balance_sheet": {
                "currency": "VND",
                "unmapped_account_codes": [],
                "lines": [{"code": "A3", "name": "Receivables", "amount": amount}],
            },
            "profit_and_loss": {
                "currency": "VND",
                "unmapped_account_codes": [],
                "lines": [{"code": "E1", "name": "Revenue", "amount": amount}],
            },
        }
        for company, amount in (("LeSC", 1000), ("LeSM", 500))
    }

    result = _aggregate_statement(
        "balance_sheet", reports, ["LeSC", "LeSM"], "2026-01-01", "2026-12-31"
    )

    assert result["currency"] == "VND"
    assert next(line for line in result["lines"] if line["code"] == "A3")["amount"] == 1500
    assert result["unmapped_account_codes"] == []


def test_consolidation_aggregates_b03_lines_fail_closed() -> None:
    reports = {
        "LeSC": {
            "cash_flow": {
                "currency": "VND",
                "unmapped_account_codes": [],
                "lines": [
                    {"code": "01", "name": "PBT", "line_type": "metric", "amount": 100, "status": "derived"},
                    {"code": "02", "name": "Depreciation", "line_type": "metric", "amount": 10, "status": "derived"},
                ],
            }
        },
        "LeSM": {
            "cash_flow": {
                "currency": "VND",
                "unmapped_account_codes": [],
                "lines": [
                    {"code": "01", "name": "PBT", "line_type": "metric", "amount": 50, "status": "derived"},
                    {"code": "02", "name": "Depreciation", "line_type": "metric", "amount": 5, "status": "derived"},
                ],
            }
        },
    }

    result = vas_reports._aggregate_cash_flow(
        reports, ["LeSC", "LeSM"], "2026-01-01", "2026-12-31"
    )

    lines = {line["code"]: line for line in result["lines"]}
    assert lines["01"]["amount"] == 150
    assert lines["02"]["amount"] == 15
    assert lines["03"]["status"] == "requires_metric"
    assert result["ok"] is False


def test_consolidated_pro_forma_applies_policy_elimination_signs() -> None:
    base = {
        "statement": "balance_sheet",
        "from_date": "2026-01-01",
        "to_date": "2026-12-31",
        "currency": "VND",
        "mapping_version": 1,
        "unmapped_account_codes": [],
        "lines": [
            {"code": "A3", "name": "Receivables", "amount": 1000},
            {"code": "C1", "name": "Payables", "amount": 1000},
        ],
    }
    schedule = [{
        "rule_code": "IC_AR_AP",
        "matching_id": "IC-001",
        "debit_account_code": "331",
        "credit_account_code": "131",
        "amount": 1000,
    }]

    result = _apply_elimination_schedule("balance_sheet", base, schedule)

    assert next(line for line in result["lines"] if line["code"] == "A3")["amount"] == 0
    assert next(line for line in result["lines"] if line["code"] == "C1")["amount"] == 0
    assert len(result["elimination_impacts"]) == 2


def test_consolidation_package_reads_holding_adjustment_book_without_double_elimination(
    monkeypatch,
) -> None:
    companies = [
        "Letron Holding",
        "LeSC",
        "LeSM",
        "LeDB",
        "LeSE",
        "LeSB",
        "LeGM",
    ]
    calls = []

    def fake_report(
        statement,
        company,
        from_date,
        to_date,
        finance_book=None,
        include_default_book_entries=False,
    ):
        calls.append((statement, company, finance_book, include_default_book_entries))
        return {
            "statement": statement,
            "company": company,
            "currency": "VND",
            "unmapped_account_codes": [],
            "lines": [],
        }

    def fake_aggregate(statement, company_reports, configured, from_date, to_date):
        return {
            "ok": True,
            "statement": statement,
            "currency": "VND",
            "unmapped_account_codes": [],
            "lines": [],
        }

    monkeypatch.setattr(
        vas_reports,
        "_consolidation_settings",
        lambda: {"holding_company": "Letron Holding", "finance_book": "Consolidation Adjustment"},
    )
    monkeypatch.setattr(vas_reports, "_configured_companies", lambda value: companies)
    monkeypatch.setattr(vas_reports, "report", fake_report)
    monkeypatch.setattr(
        vas_reports,
        "statutory_cash_flow",
        lambda *args, **kwargs: {
            "currency": "VND",
            "unmapped_account_codes": [],
            "lines": [],
        },
    )
    monkeypatch.setattr(vas_reports, "elimination_schedule", lambda *args: [])
    monkeypatch.setattr(vas_reports, "intercompany_matches", lambda *args: [])
    monkeypatch.setattr(vas_reports, "_aggregate_statement", fake_aggregate)
    monkeypatch.setattr(vas_reports, "_apply_elimination_schedule", lambda *args: args[1])

    result = vas_reports.consolidation_package(
        companies,
        "2026-01-01",
        "2026-12-31",
        include_adjustments=True,
        comparative_from_date="2025-01-01",
        comparative_to_date="2025-12-31",
    )

    assert result["native_adjustment_readback"] == {
        "finance_book": "Consolidation Adjustment",
        "holding_company": "Letron Holding",
        "status": "derived_from_native_gl",
    }
    assert [call for call in calls if call[2] == "Consolidation Adjustment"] == [
        ("balance_sheet", "Letron Holding", "Consolidation Adjustment", True),
        ("profit_and_loss", "Letron Holding", "Consolidation Adjustment", True),
        ("balance_sheet", "Letron Holding", "Consolidation Adjustment", True),
        ("profit_and_loss", "Letron Holding", "Consolidation Adjustment", True),
    ]
    assert "cash_flow" in result["consolidated_after_native_adjustment_comparative"]


def test_consolidation_package_builds_comparative_period_without_writing_gl(
    monkeypatch,
) -> None:
    companies = [
        "Letron Holding",
        "LeSC",
        "LeSM",
        "LeDB",
        "LeSE",
        "LeSB",
        "LeGM",
    ]

    def fake_report(statement, company, from_date, to_date, **kwargs):
        amount = 2026 if from_date.startswith("2026") else 2025
        line_code = "A1" if statement == "balance_sheet" else "E1"
        return {
            "statement": statement,
            "company": company,
            "currency": "VND",
            "unmapped_account_codes": [],
            "lines": [{"code": line_code, "name": line_code, "amount": amount}],
        }

    def fake_cash_flow(company, from_date, to_date, **kwargs):
        amount = 2026 if from_date.startswith("2026") else 2025
        return {
            "currency": "VND",
            "unmapped_account_codes": [],
            "lines": [
                {
                    "code": "01",
                    "name": "PBT",
                    "line_type": "metric",
                    "amount": amount,
                    "status": "derived",
                    "comparative_amount": amount - 1,
                    "comparative_status": "derived",
                }
            ],
        }

    monkeypatch.setattr(
        vas_reports,
        "_consolidation_settings",
        lambda: {
            "holding_company": "Letron Holding",
            "finance_book": "Consolidation Adjustment",
        },
    )
    monkeypatch.setattr(vas_reports, "_configured_companies", lambda value: companies)
    monkeypatch.setattr(vas_reports, "report", fake_report)
    monkeypatch.setattr(vas_reports, "statutory_cash_flow", fake_cash_flow)
    monkeypatch.setattr(vas_reports, "elimination_schedule", lambda *args: [])
    monkeypatch.setattr(vas_reports, "intercompany_matches", lambda *args: [])

    result = vas_reports.consolidation_package(
        companies,
        "2026-01-01",
        "2026-12-31",
        comparative_from_date="2025-01-01",
        comparative_to_date="2025-12-31",
    )

    assert result["comparative_from_date"] == "2025-01-01"
    assert result["comparative_to_date"] == "2025-12-31"
    assert result["comparative_elimination_schedule"] == []
    assert next(
        line
        for line in result["consolidated_before_elimination_comparative"]["balance_sheet"]["lines"]
        if line["code"] == "A1"
    )["amount"] == 2025 * len(companies)
    assert next(
        line
        for line in result["consolidated_cash_flow"]["lines"]
        if line["code"] == "01"
    )["comparative_amount"] == 2025 * len(companies)


def test_consolidated_cash_flow_uses_comparative_period_exchange_rate(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        vas_reports,
        "_statutory_form",
        lambda code: {
            "name": "Cash Flow",
            "columns": ["current_period", "comparative_period"],
            "lines": [
                {
                    "code": "01",
                    "name": "Profit before tax",
                    "line_type": "metric",
                    "metric": "profit_before_tax",
                }
            ]
        },
    )
    monkeypatch.setattr(
        vas_reports,
        "_currency_policy",
        lambda: {"reporting_currency": "VND"},
    )
    monkeypatch.setattr(
        vas_reports,
        "_exchange_rate",
        lambda source, target, rate_date: {
            "2026-12-31": 2.0,
            "2025-12-31": 3.0,
        }[rate_date],
    )

    result = _aggregate_cash_flow(
        {
            "LeSC": {
                "cash_flow": {
                    "currency": "USD",
                    "unmapped_account_codes": [],
                    "lines": [
                        {
                            "code": "01",
                            "amount": 10,
                            "status": "derived",
                            "comparative_amount": 10,
                            "comparative_status": "derived",
                        }
                    ],
                }
            }
        },
        ["LeSC"],
        "2026-01-01",
        "2026-12-31",
        comparative_from_date="2025-01-01",
        comparative_to_date="2025-12-31",
    )

    line = result["lines"][0]
    assert line["amount"] == 20.0
    assert line["comparative_amount"] == 30.0
    assert result["currency_conversion"]["rate_date"] == "2026-12-31"
    assert result["comparative_currency_conversion"]["rate_date"] == "2025-12-31"


def test_consolidation_adjustment_allows_native_ar_ap_elimination_without_parties(
    monkeypatch,
) -> None:
    class FakeDB:
        def get_value(self, doctype, filters, field=None):
            if doctype == "Journal Entry":
                return None
            if doctype == "Account":
                assert filters["company"] == "Letron Holding"
                return f"{filters['account_number']} - LTVN"
            raise AssertionError(f"unexpected lookup: {doctype}")

    class FakeDoc:
        name = "ACC-JV-TEST"
        docstatus = 0

        def __init__(self, payload):
            self.payload = payload

        def insert(self, **kwargs):
            return self

    class FakeFrappe:
        ValidationError = ValueError

        def __init__(self):
            self.db = FakeDB()
            self.document = None

        def get_doc(self, payload):
            self.document = FakeDoc(payload)
            return self.document

        def throw(self, message, exc=None):
            raise (exc or ValueError)(message)

    frappe = FakeFrappe()
    monkeypatch.setattr(vas_reports, "_frappe", lambda: frappe)
    monkeypatch.setattr(
        vas_reports,
        "_consolidation_settings",
        lambda: {
            "holding_company": "Letron Holding",
            "finance_book": "Consolidation Adjustment",
        },
    )
    monkeypatch.setattr(vas_reports, "_configured_companies", lambda value: value)
    monkeypatch.setattr(vas_reports, "_consolidation_cost_center", lambda value: "HLD-FIN - LTVN")
    monkeypatch.setattr(
        vas_reports,
        "elimination_schedule",
        lambda *args: [
            {
                "rule_code": "IC_AR_AP",
                "matching_id": "IC-001",
                "debit_account_code": "331",
                "credit_account_code": "131",
                "amount": 1000,
            }
        ],
    )

    result = vas_reports.create_consolidation_adjustment(
        ["Letron Holding", "LeSC"],
        "2026-01-01",
        "2026-01-31",
        "2026-01-31",
        "RUN-001",
    )

    assert result["journal_entry"] == "ACC-JV-TEST"
    assert frappe.document.payload["party_not_required"] == 1
    assert len(frappe.document.payload["accounts"]) == 2


def test_vas_reporting_policy_declares_vas24_cash_flow_contract() -> None:
    cash_flow = _cash_flow_policy()

    assert cash_flow["standard"] == "VAS 24"
    assert cash_flow["method"] == "indirect"
    assert set(cash_flow["categories"]) == {"operating", "investing", "financing"}
    assert "Depreciation" in cash_flow["categories"]["operating"]["native_account_types"]
    assert {
        "provisions",
        "fx_revaluation",
        "borrowing_cost",
        "payables_change_excluding_interest_and_tax",
        "fixed_asset_purchases",
        "borrowings_proceeds",
        "dividends_and_profit_distributions",
        "translation_fx_effect",
    } <= set(cash_flow["metric_sources"])


def test_native_cash_flow_account_type_query_receives_company_filter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FrappeDict(dict):
        __getattr__ = dict.get

        def __setattr__(self, key, value):
            self[key] = value

    class FakeFrappe:
        _dict = FrappeDict

    native = ModuleType("erpnext.accounts.report.cash_flow.cash_flow")
    native.get_period_list = lambda *args, **kwargs: [{"to_date": "2026-12-31"}]
    native.get_start_date = lambda period, accumulated_values, company: "2026-01-01"

    def fake_account_type_data(company, filters):
        captured["company_argument"] = company
        captured["filters"] = dict(filters)
        return 10

    native.get_account_type_based_gl_data = fake_account_type_data
    monkeypatch.setitem(sys.modules, native.__name__, native)
    monkeypatch.setattr(vas_reports, "_frappe", lambda: FakeFrappe())

    result = vas_reports._native_cash_flow_account_type_change(
        "LeSC", "2026-01-01", "2026-12-31", "Depreciation"
    )

    assert result == -10
    assert captured["company_argument"] == "LeSC"
    assert captured["filters"]["company"] == "LeSC"


def test_note_snapshot_resolves_native_statement_values_without_inventing_text() -> None:
    statements = {
        "balance_sheet": {
            "lines": [{"code": "A1", "name": "Cash", "amount": 1250}],
            "unmapped_account_codes": [],
        },
        "profit_and_loss": {
            "lines": [{"code": "E1", "name": "Revenue", "amount": 800}],
            "unmapped_account_codes": [],
        },
    }

    result = _note_snapshot(
        {"code": "N02", "name": "Cash", "source": "balance_sheet.A1"},
        statements,
    )

    assert result == {
        "source": "balance_sheet.A1",
        "status": "derived",
        "data": {
            "balance_sheet.A1": {"code": "A1", "name": "Cash", "amount": 1250}
        },
    }


def test_consolidated_lines_do_not_expose_account_mapping_implementation_details() -> None:
    reports = {
        "LeSC": {
            "balance_sheet": {
                "currency": "VND",
                "unmapped_account_codes": [],
                "lines": [{"code": "A3", "name": "Receivables", "amount": 10}],
            }
        }
    }

    result = _aggregate_statement(
        "balance_sheet", reports, ["LeSC"], "2026-01-01", "2026-12-31"
    )
    line = next(item for item in result["lines"] if item["code"] == "A3")

    assert set(line) == {"code", "name", "amount", "classification"}
