"""Acceptance for the Git-backed native ERPNext policy bundle."""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest
import yaml
from letron_api.policy import load_policy, policy_sha256
from letron_api.system_config import load_config

from .api_runtime_harness import ApiClient, RuntimeUnavailable, response_data

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def bench_execute(method: str) -> str:
    config = load_config(ROOT / "config" / "config.yaml")
    result = subprocess.run(
        [
            "docker",
            "exec",
            f"{config['project']['name']}-backend-1",
            "bench",
            "--site",
            config["site"]["name"],
            "execute",
            method,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout


def test_policy_bundle_matches_and_protects_native_configuration() -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    bundle = load_policy()
    expected_hash = policy_sha256(bundle)
    exported = yaml.safe_load(base64.b64decode(bench_execute("letron_api.policy.export_current_base64")))
    assert exported == bundle
    assert len(bundle["documents"]) == 15
    snapshot = client.request("GET", "/api/method/letron_api.api.runtime_snapshot", expected={200})
    bootstrap = snapshot.data["message"]["bootstrap"]
    assert bootstrap["ok"] is True
    assert bootstrap["company_count"] == 1
    assert bootstrap["company_matches"] is True
    assert {key: value["rates"] for key, value in bootstrap["templates"].items()} == {
        "sales": [10.0],
        "purchase": [10.0],
        "item": [10.0],
    }
    runtime_policy = snapshot.data["message"]["policy"]
    assert runtime_policy == {
        "ok": True,
        "version": 1,
        "erpnext_version": bundle["erpnext_version"],
        "sha256": expected_hash,
        "documents": len(bundle["documents"]),
        "drift_count": 0,
        "status": "in-sync",
    }

    accounts_entry = next(
        entry for entry in bundle["documents"] if entry["doctype"] == "Accounts Settings"
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
    assert not any(entry["doctype"] == "Video Settings" for entry in bundle["documents"])
    assert not any(entry["doctype"] == "CRM Settings" for entry in bundle["documents"])

    # Policy is deployment configuration, not another public business API.
    client.request("GET", "/api/v1/config/business-policies", expected={404})

    try:
        bench_execute("letron_api.policy.acceptance_force_drift")
        drifted = client.request(
            "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
        ).data["message"]["policy"]
        assert drifted["ok"] is False
        assert drifted["status"] == "drifted"
        assert drifted["drift_count"] == 1
    finally:
        bench_execute("letron_api.policy.sync")

    restored = client.request(
        "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
    ).data["message"]["policy"]
    assert restored["ok"] is True and restored["drift_count"] == 0
    assert '"applied": 0' in bench_execute("letron_api.policy.sync")


def test_compute_yaml_control_api_is_fixed_path_and_idempotent() -> None:
    client = ApiClient()
    try:
        client.health_and_login()
    except RuntimeUnavailable as error:
        pytest.fail(f"blocked runtime: {error}")

    guest = ApiClient()
    guest.request(
        "GET",
        "/api/method/letron_api.config_control.get_configuration?kind=config",
        expected={401, 403},
    )

    snapshot = client.request(
        "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
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

    current_by_kind = {}
    for kind in ("config", "policy"):
        current = client.request(
            "GET",
            f"/api/method/letron_api.config_control.get_configuration?kind={kind}",
            expected={200},
        ).data["message"]
        current_by_kind[kind] = current
        assert "content" in current and current["source_sha256"]
        if kind == "config":
            assert "${DB_ROOT_PASSWORD}" in current["content"]
            assert (
                load_config(resolve_secrets=True)["database"]["root_password"]
                not in current["content"]
            )
        updated = client.request(
            "PUT",
            "/api/method/letron_api.config_control.put_configuration",
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

    original_config = current_by_kind["config"]["content"]
    changed_config = original_config.replace("proxy_timeout: 120", "proxy_timeout: 121", 1)
    assert changed_config != original_config
    try:
        changed = client.request(
            "PUT",
            "/api/method/letron_api.config_control.put_configuration",
            {
                "kind": "config",
                "content": changed_config,
                "expected_source_sha256": current_by_kind["config"]["source_sha256"],
                "apply_now": 1,
            },
            expected={200},
        ).data["message"]
        assert changed["restart_required"] is True
        readback = client.request(
            "GET",
            "/api/method/letron_api.config_control.get_configuration?kind=config",
            expected={200},
        ).data["message"]
        assert "proxy_timeout: 121" in readback["content"]
    finally:
        live = client.request(
            "GET",
            "/api/method/letron_api.config_control.get_configuration?kind=config",
            expected={200},
        ).data["message"]
        if live["content"] != original_config:
            restored_source = client.request(
                "PUT",
                "/api/method/letron_api.config_control.put_configuration",
                {
                    "kind": "config",
                    "content": original_config,
                    "expected_source_sha256": live["source_sha256"],
                    "apply_now": 1,
                },
                expected={200},
            ).data["message"]
            assert restored_source["restart_required"] is True

    client.request(
        "PUT",
        "/api/method/letron_api.config_control.put_configuration",
        {
            "kind": "config",
            "content": current_by_kind["config"]["content"],
            "expected_source_sha256": "0" * 64,
        },
        expected={409},
    )

    # A structurally valid source that fails native runtime validation must
    # restore both the exact YAML bytes and the previous runtime state.
    before_failure = client.request(
        "GET",
        "/api/method/letron_api.config_control.get_configuration?kind=config",
        expected={200},
    ).data["message"]
    invalid_runtime_config = before_failure["content"].replace(
        "system_settings:\n", "system_settings:\n  acceptance_unknown_native_field: 1\n", 1
    )
    client.request(
        "PUT",
        "/api/method/letron_api.config_control.put_configuration",
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
        "/api/method/letron_api.config_control.get_configuration?kind=config",
        expected={200},
    ).data["message"]
    assert after_failure["content"] == before_failure["content"]
    assert after_failure["source_sha256"] == before_failure["source_sha256"]
    assert client.request(
        "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
    ).data["message"]["config"]["ok"] is True

    policy_source = current_by_kind["policy"]
    renamed_company = policy_source["content"].replace(
        "name: Letron Việt Nam", "name: Letron Việt Nam Renamed", 1
    )
    client.request(
        "PUT",
        "/api/method/letron_api.config_control.put_configuration",
        {
            "kind": "policy",
            "content": renamed_company,
            "expected_source_sha256": policy_source["source_sha256"],
            "apply_now": 1,
        },
        expected={409},
    )

    try:
        bench_execute("letron_api.system_config.acceptance_force_drift")
        drifted = client.request(
            "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
        ).data["message"]["config"]
        assert drifted["ok"] is False and drifted["drift_count"] == 1
    finally:
        bench_execute("letron_api.system_config.sync")
    restored = client.request(
        "GET", "/api/method/letron_api.api.runtime_snapshot", expected={200}
    ).data["message"]["config"]
    assert restored["ok"] is True and restored["drift_count"] == 0
    client.request(
        "GET",
        "/api/method/letron_api.config_control.get_configuration?kind=arbitrary-file",
        expected={400, 417},
    )
