"""Acceptance for the Git-backed native ERPNext policy bundle."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from letron_api.control.policy import load_policy, policy_sha256
from letron_api.control.policy_acceptance import DOCUMENT_BUILDERS, SINGLE_BUILDERS
from letron_api.control.system_config import load_config

from .test_api_runtime_harness import ApiClient, RuntimeUnavailable, response_data

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def bench_execute(method: str, kwargs: dict[str, object] | None = None) -> str:
    config = load_config(_runtime_config_path())
    # Acceptance probes are rollback-only and guarded by _is_test_runtime.
    # Enable that guard only in this short-lived bench process; do not change
    # the persisted production-like config or the long-running containers.
    kwargs_expression = repr(kwargs or {})
    method_expression = (
        "(lambda f: (setattr(f.conf, 'developer_mode', 1), "
        "setattr(f.conf, 'allow_tests', 1), "
        f"f.get_attr('{method}')(**{kwargs_expression}))[-1])(__import__('frappe'))"
    )
    command = [
        "docker",
        "exec",
        "-w",
        "/home/frappe/frappe-bench",
        f"{config['project']['name']}-backend-1",
        "bench",
        "--site",
        config["site"]["name"],
        "execute",
        method_expression,
    ]
    if kwargs:
        command.extend(["--kwargs", json.dumps(kwargs)])
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout


def _runtime_config_path() -> Path:
    return ROOT / "config" / "config.yaml"


def _logged_in_client() -> ApiClient:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")
    return client


def test_policy_bundle_matches_native_configuration() -> None:
    client = _logged_in_client()

    bundle = load_policy(_runtime_config_path().parent / "policy.yaml")
    expected_hash = policy_sha256(bundle)
    exported = yaml.safe_load(
        base64.b64decode(bench_execute("letron_api.control.policy.export_current_base64"))
    )
    assert exported == bundle
    assert len(bundle["documents"]) == 69
    snapshot = client.request(
        "GET", "/api/method/letron_api.control.api.runtime_snapshot", expected={200}
    )
    bootstrap = snapshot.data["message"]["bootstrap"]
    assert bootstrap["ok"] is True
    assert bootstrap["company_count"] == 8
    assert bootstrap["transaction_company_count"] == 7
    assert bootstrap["company_matches"] is True
    assert bootstrap["group_matches"] is True
    assert bootstrap["fiscal_year"] == {
        "ok": True,
        "configured": True,
        "name": "2026",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "companies": ["LeDB", "LeGM", "LeSC", "LeSE", "LeSB", "LeSM", "Letron Holding"],
        "expected_companies": ["LeDB", "LeGM", "LeSC", "LeSE", "LeSB", "LeSM", "Letron Holding"],
        "native_exists": True,
    }
    assert {key: value["rates"] for key, value in bootstrap["templates"].items()} == {
        "sales": [10.0],
        "purchase": [10.0],
        "item": [10.0],
    }
    runtime_policy = snapshot.data["message"]["policy"]
    assert runtime_policy == {
        "ok": True,
        "version": 3,
        "schema_version": 3,
        "scope_version": 1,
        "erpnext_version": bundle["erpnext_version"],
        "sha256": expected_hash,
        "documents": len(bundle["documents"]),
        "drift_count": 0,
        "completeness": {
            "unclassified_sources": 0,
            "managed_entries_without_acceptance": 0,
            "schema_drift": 0,
            "unmanaged_policy_records": 0,
            "runtime_drift": 0,
            "roundtrip_diff": 0,
        },
        "status": "in-sync",
        "bootstrap_companies": ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"],
        "bootstrap_group": {"name": "LETRON GROUP", "abbreviation": "LTRG"},
    }

    accounts_entry = next(
        entry
        for entry in bundle["documents"]
        if entry["doctype"] == "Accounts Settings"
    )
    native = response_data(
        client.document("GET", "Accounts Settings", "Accounts Settings", expected={200})
    )
    for fieldname, expected in accounts_entry["fields"].items():
        if fieldname != "repost_allowed_types":
            assert native.get(fieldname) == expected
    assert [row["document_type"] for row in native["repost_allowed_types"]] == [
        row["document_type"] for row in accounts_entry["fields"]["repost_allowed_types"]
    ]


def test_policy_bundle_protects_native_configuration() -> None:
    client = _logged_in_client()
    bundle = load_policy(_runtime_config_path().parent / "policy.yaml")
    native = response_data(
        client.document("GET", "Accounts Settings", "Accounts Settings", expected={200})
    )

    original = native["check_supplier_invoice_uniqueness"]
    client.document(
        "PUT",
        "Accounts Settings",
        "Accounts Settings",
        {"check_supplier_invoice_uniqueness": 0 if original else 1},
        expected={403, 417},
    )
    persisted = response_data(
        client.document("GET", "Accounts Settings", "Accounts Settings", expected={200})
    )
    assert persisted["check_supplier_invoice_uniqueness"] == original

    assert "access_key" not in next(
        entry["fields"]
        for entry in bundle["documents"]
        if entry["doctype"] == "Currency Exchange Settings"
    )
    assert not any(
        entry["doctype"] == "Video Settings" for entry in bundle["documents"]
    )
    assert not any(entry["doctype"] == "CRM Settings" for entry in bundle["documents"])

    # Policy is deployment configuration, not another public business API.
    client.request("GET", "/api/v1/config/business-policies", expected={404})


def test_policy_drift_and_idempotent_restore() -> None:
    drift = json.loads(bench_execute("letron_api.control.policy.acceptance_force_drift"))
    assert drift["drift_count"] == 1
    try:
        restored = json.loads(bench_execute("letron_api.control.policy.sync"))
        assert restored["ok"] is True
        assert restored["drift_count"] == 0
    finally:
        # Make cleanup idempotent even when the assertions above fail.
        bench_execute("letron_api.control.policy.sync")

    second_sync = json.loads(bench_execute("letron_api.control.policy.sync"))
    assert second_sync["applied"] == 0


def _control_client() -> ApiClient:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")
    return client


def _configuration_source(client: ApiClient, kind: str) -> dict[str, Any]:
    return client.request(
        "GET",
        f"/api/method/letron_api.control.config_control.get_configuration?kind={kind}",
        expected={200},
    ).data["message"]


def test_compute_yaml_control_api_access_and_idempotency() -> None:
    client = _control_client()

    guest = ApiClient()
    guest.request(
        "GET",
        "/api/method/letron_api.control.config_control.get_configuration?kind=config",
        expected={401, 403},
    )

    snapshot = client.request(
        "GET", "/api/method/letron_api.control.api.runtime_snapshot", expected={200}
    ).data["message"]
    assert snapshot["config"]["ok"] is True
    assert snapshot["config"]["drift_count"] == 0
    system_settings = response_data(
        client.document("GET", "System Settings", "System Settings", expected={200})
    )
    original_password_policy = system_settings["enable_password_policy"]
    client.document(
        "PUT",
        "System Settings",
        "System Settings",
        {"enable_password_policy": 0 if original_password_policy else 1},
        expected={403, 417},
    )

    for kind in ("config", "policy"):
        current = _configuration_source(client, kind)
        assert "content" in current and current["source_sha256"]
        if kind == "config":
            assert "${LETRON_BOOTSTRAP_PASSWORD}" in current["content"]
            assert (
                load_config(resolve_secrets=True)["database"]["root_password"]
                not in current["content"]
            )
        updated = client.request(
            "PUT",
            "/api/method/letron_api.control.config_control.put_configuration",
            {
                "kind": kind,
                "content": current["content"],
                "expected_source_sha256": current["source_sha256"],
                "apply_now": 1,
            },
            expected={200},
        ).data["message"]
        assert updated["ok"] is True
        assert updated["applied"] == 0
        assert updated["drift_count"] == 0


def test_compute_yaml_control_api_update_and_restore() -> None:
    client = _control_client()
    current = _configuration_source(client, "config")
    original_config = current["content"]
    changed_config = original_config.replace(
        "proxy_timeout: 120", "proxy_timeout: 121", 1
    )
    assert changed_config != original_config
    try:
        changed = client.request(
            "PUT",
            "/api/method/letron_api.control.config_control.put_configuration",
            {
                "kind": "config",
                "content": changed_config,
                "expected_source_sha256": current["source_sha256"],
                "apply_now": 1,
            },
            expected={200},
        ).data["message"]
        assert changed["restart_required"] is True
        readback = client.request(
            "GET",
            "/api/method/letron_api.control.config_control.get_configuration?kind=config",
            expected={200},
        ).data["message"]
        assert "proxy_timeout: 121" in readback["content"]
    finally:
        live = client.request(
            "GET",
            "/api/method/letron_api.control.config_control.get_configuration?kind=config",
            expected={200},
        ).data["message"]
        if live["content"] != original_config:
            restored_source = client.request(
                "PUT",
                "/api/method/letron_api.control.config_control.put_configuration",
                {
                    "kind": "config",
                    "content": original_config,
                    "expected_source_sha256": live["source_sha256"],
                    "apply_now": 1,
                },
                expected={200},
            ).data["message"]
            assert restored_source["restart_required"] is True


def test_compute_yaml_control_api_conflict_and_atomic_rollback() -> None:
    client = _control_client()
    current = _configuration_source(client, "config")
    client.request(
        "PUT",
        "/api/method/letron_api.control.config_control.put_configuration",
        {
            "kind": "config",
            "content": current["content"],
            "expected_source_sha256": "0" * 64,
        },
        expected={409},
    )

    # A structurally valid source that fails native runtime validation must
    # restore both the exact YAML bytes and the previous runtime state.
    before_failure = client.request(
        "GET",
        "/api/method/letron_api.control.config_control.get_configuration?kind=config",
        expected={200},
    ).data["message"]
    invalid_runtime_config = before_failure["content"].replace(
        "system_settings:\n",
        "system_settings:\n  acceptance_unknown_native_field: 1\n",
        1,
    )
    client.request(
        "PUT",
        "/api/method/letron_api.control.config_control.put_configuration",
        {
            "kind": "config",
            "content": invalid_runtime_config,
            "expected_source_sha256": before_failure["source_sha256"],
            "apply_now": 1,
        },
        expected={417, 500},
    )
    after_failure = client.request(
        "GET",
        "/api/method/letron_api.control.config_control.get_configuration?kind=config",
        expected={200},
    ).data["message"]
    assert after_failure["content"] == before_failure["content"]
    assert after_failure["source_sha256"] == before_failure["source_sha256"]
    assert (
        client.request(
            "GET", "/api/method/letron_api.control.api.runtime_snapshot", expected={200}
        ).data["message"]["config"]["ok"]
        is True
    )



def test_compute_yaml_control_api_policy_boundary_and_drift() -> None:
    client = _control_client()
    policy_source = _configuration_source(client, "policy")
    renamed_company = policy_source["content"].replace(
        "name: Letron Holding", "name: Letron Holding Renamed", 1
    )
    client.request(
        "PUT",
        "/api/method/letron_api.control.config_control.put_configuration",
        {
            "kind": "policy",
            "content": renamed_company,
            "expected_source_sha256": policy_source["source_sha256"],
            "apply_now": 1,
        },
        expected={409},
    )

    try:
        bench_execute("letron_api.control.system_config.acceptance_force_drift")
        drifted = json.loads(bench_execute("letron_api.control.system_config.plan"))
        assert drifted["ok"] is False and drifted["drift_count"] == 1
    finally:
        bench_execute("letron_api.control.system_config.sync")
    restored = json.loads(bench_execute("letron_api.control.system_config.plan"))
    assert restored["ok"] is True and restored["drift_count"] == 0
    client.request(
        "GET",
        "/api/method/letron_api.control.config_control.get_configuration?kind=arbitrary-file",
        expected={400, 417},
    )


REGISTRY_SOURCES = sorted(SINGLE_BUILDERS | DOCUMENT_BUILDERS.keys())
STRUCTURAL_SHARDS = [
    REGISTRY_SOURCES[index : index + 8] for index in range(0, len(REGISTRY_SOURCES), 8)
]
DOCUMENT_SOURCES = sorted(DOCUMENT_BUILDERS)
APPLY_SHARDS = [
    DOCUMENT_SOURCES[index : index + 4] for index in range(0, len(DOCUMENT_SOURCES), 4)
]


@pytest.mark.parametrize("doctypes", STRUCTURAL_SHARDS)
def test_registry_driven_native_structural_group(doctypes: list[str]) -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_structural_sources",
            {"doctypes": doctypes},
        )
    )
    assert result["ok"] is True
    assert result["passed"] == len(doctypes)


@pytest.mark.parametrize("doctypes", APPLY_SHARDS)
def test_registry_driven_policy_apply_roundtrip(doctypes: list[str]) -> None:
    apply_result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_policy_apply_registry",
            {"doctypes": doctypes},
        )
    )
    assert apply_result["ok"] is True
    assert apply_result["sources"] == len(doctypes)
    assert apply_result["first_applied"] > 0
    assert apply_result["second_applied"] == 0
    assert apply_result["removed"] > 0
    assert apply_result["roundtrip_diff"] == 0


def test_registry_driven_asset_lifecycle() -> None:
    asset_result = json.loads(
        bench_execute("letron_api.control.policy_acceptance.probe_asset_lifecycle")
    )
    assert asset_result["ok"] is True
    assert asset_result["public_private"] == 2
    assert asset_result["checksum_conflict"] == "rejected"
    assert asset_result["traversal"] == "rejected"
    assert asset_result["collision"] == "rejected"
    assert asset_result["rollback"] == "byte-clean"

    cleanup = json.loads(
        bench_execute("letron_api.control.policy_acceptance.cleanup_registry_residue")
    )
    assert cleanup["ok"] is True


@pytest.mark.parametrize("rate", [0, 5, 8, 10])
def test_policy_tax_invoice_gl_effect(rate: int) -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_tax_effect_rate", {"rate": rate}
        )
    )
    assert result["ok"] is True
    assert result["rate"] == rate
    assert result["tax"] == 1000 * rate
    assert result["sales_gl"] == result["tax"]
    assert result["purchase_gl"] == result["tax"]


def test_policy_configured_tax_categories_and_rules_readback() -> None:
    result = json.loads(bench_execute("letron_api.control.policy_acceptance.probe_configured_tax_policy"))
    assert result["ok"] is True
    assert result["selected"] == {
        "software_sales": "Vietnam Software Non-VAT - LTVN",
        "software_purchase": "Vietnam Software Non-VAT - LTVN",
        "hosting_sales": "Vietnam Tax - LTVN",
        "hosting_purchase": "Vietnam Tax - LTVN",
    }


def test_policy_configured_fiscal_year_readback() -> None:
    result = json.loads(bench_execute("letron_api.control.policy_acceptance.probe_configured_fiscal_year"))
    assert result["ok"] is True
    assert result["fiscal_year"] == "2026"
    assert result["start_date"] == "2026-01-01"
    assert result["end_date"] == "2026-12-31"
    assert result["companies"] == [
        "LeDB", "LeGM", "LeSB", "LeSC", "LeSE", "LeSM", "Letron Holding"
    ]
    assert result["comparative_fiscal_years"] == [{
        "fiscal_year": "2025",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "companies": [
            "LeDB", "LeGM", "LeSB", "LeSC", "LeSE", "LeSM", "Letron Holding"
        ],
    }]
    assert result["accounting_period_placeholder"] == "absent"


def test_holding_consolidation_uses_native_je_gl_and_guard() -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_holding_consolidation_effects"
        )
    )
    assert result["ok"] is True
    assert result["match_balanced"] is True
    assert result["gl_entry_count"] >= 4
    assert result["schedule_rule_codes"] == ["IC_AR_AP", "IC_REVENUE_COST"]
    assert result["schedule_amounts"] == [1000.0]
    assert result["adjustment_mode"] in {
        "closed_period_guard",
        "native_adjustment_and_idempotency",
    }


@pytest.mark.timeout(180)
def test_holding_synthetic_vas_acceptance() -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_holding_synthetic_vas_acceptance"
        )
    )
    assert result["ok"] is True
    assert result["profile"] == "synthetic_vas"
    assert result["scope"] == {
        "companies": ["Letron Holding", "LeSC", "LeSM", "LeDB", "LeSE", "LeSB", "LeGM"],
        "currency": "VND",
        "coa": "generic_tt99",
        "native_gl_only": True,
    }
    assert result["periods"] == {
        "current": ["2026-06-01", "2026-06-30"],
        "comparative": ["2025-06-01", "2025-06-30"],
    }
    assert result["native"]["gl_entries"] > result["native"]["journal_entries"]
    assert result["native"]["bank_account"] is True
    assert result["native"]["asset_category"] is True
    assert result["native"]["inventory_warehouse"] is True
    assert result["reports"]["B03-DN"]["unresolved_line_codes"] == []
    assert result["reports"]["B01-DN"]["unresolved_line_codes"] == []
    assert result["reports"]["B02-DN"]["unresolved_line_codes"] == []
    assert result["reports"]["B03-DN"]["comparative"]["status"] == "derived"
    assert result["notes"]["note_count"] >= 7
    assert result["consolidation"]["companies"] == 7
    assert result["consolidation"]["comparative"] is True
    assert result["consolidation"]["schedule_rule_codes"] == ["IC_AR_AP", "IC_REVENUE_COST"]
    assert result["consolidation"]["adjustment_location"] == (
        "Letron Holding/Consolidation Adjustment"
    )


def test_policy_configured_tax_invoice_effects() -> None:
    result = json.loads(
        bench_execute("letron_api.control.policy_acceptance.probe_configured_tax_invoice_effects")
    )
    assert result["ok"] is True
    assert result["observed"] == {
        "software": {"sales_tax": 0.0, "purchase_tax": 0.0, "sales_gl": 0.0, "purchase_gl": 0.0},
        "hosting": {"sales_tax": 10000.0, "purchase_tax": 10000.0, "sales_gl": 10000.0, "purchase_gl": 10000.0},
        "transport": {"sales_tax": 10000.0, "purchase_tax": 10000.0, "sales_gl": 10000.0, "purchase_gl": 10000.0},
    }


@pytest.mark.parametrize(
    "method",
    [
        "letron_api.control.policy_acceptance.probe_payment_terms_effect",
        "letron_api.control.policy_acceptance.probe_pricing_shipping_effects",
        "letron_api.control.policy_acceptance.probe_stock_buying_effects",
    ],
)
def test_policy_controller_effect_group(method: str) -> None:
    result = json.loads(bench_execute(method))
    assert result["ok"] is True


@pytest.mark.parametrize(
    "effect", ["render", "naming", "notification_assignment", "workflow_permission"]
)
def test_policy_cross_cutting_effect(effect: str) -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_cross_cutting_effects",
            {"effect": effect},
        )
    )
    assert result["ok"] is True
    assert result["effect"] == effect


@pytest.mark.parametrize(
    "step",
    [
        "after-assets",
        "after-documents",
        "after-deletes",
        "before-cache",
        "before-commit",
    ],
)
def test_policy_failure_rollback(step: str) -> None:
    result = json.loads(
        bench_execute(
            "letron_api.control.policy_acceptance.probe_failure_rollback", {"step": step}
        )
    )
    assert result == {
        "ok": True,
        "step": step,
        "document_restored": True,
        "asset_restored": True,
        "yaml_unchanged": True,
        "cache_restored": True,
    }
