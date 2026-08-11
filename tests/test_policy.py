from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from letron_api import policy


def write_policy(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_repository_policy_is_valid_and_deterministic() -> None:
    first = policy.load_policy()
    second = policy.load_policy()

    assert first == second
    assert policy.policy_sha256(first) == policy.policy_sha256(second)
    assert policy.validate_file()["documents"] == len(first["documents"])
    assert {entry["doctype"] for entry in first["documents"]} <= set(policy.POLICY_DOCTYPES)
    assert first["bootstrap"]["company"] == {
        "name": "Letron Việt Nam",
        "abbreviation": "LTVN",
        "country": "Vietnam",
        "currency": "VND",
        "domain": "Distribution",
        "chart_of_accounts": "Standard",
    }


def test_every_native_erpnext_single_is_managed_or_explicitly_transient() -> None:
    erpnext_root = Path(__file__).parents[1] / "apps" / "erpnext" / "erpnext"
    native_singles: set[str] = set()
    for path in erpnext_root.glob("**/doctype/*/*.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(metadata, dict) and metadata.get("issingle") == 1 and not metadata.get("istable"):
            native_singles.add(metadata.get("name") or path.stem)

    assert native_singles == policy.SINGLE_DOCTYPES | policy.TRANSIENT_SINGLE_DOCTYPES
    assert policy.SINGLE_DOCTYPES.isdisjoint(policy.TRANSIENT_SINGLE_DOCTYPES)


def test_non_password_native_credentials_are_excluded() -> None:
    class Field:
        fieldname = "access_key"
        fieldtype = "Data"
        is_virtual = False

    class Meta:
        def __init__(self) -> None:
            self.fields = [Field()]

    assert policy._managed_field_names(Meta(), "Currency Exchange Settings") == []


def test_business_configuration_inventory_tracks_bundle_and_native_single_sources() -> None:
    root = Path(__file__).parents[1]
    inventory_path = root / "docs" / "Configuration_Inventory.md"
    inventory = inventory_path.read_text(encoding="utf-8")
    bundle = policy.load_policy()

    assert f"{len(bundle['documents'])} document" in inventory
    assert "\ufffd" not in inventory

    native_single_files: set[str] = set()
    for path in (root / "apps" / "erpnext" / "erpnext").glob("**/doctype/*/*.json"):
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(metadata, dict) and metadata.get("issingle") == 1 and not metadata.get("istable"):
            native_single_files.add(path.name)
    assert native_single_files
    assert all(filename in inventory for filename in native_single_files)

    for target in re.findall(r"]\(([^)]+)\)", inventory):
        if "://" not in target and not target.startswith("#"):
            assert (inventory_path.parent / target).resolve().exists(), target


def test_policy_round_trips_unicode_and_native_child_rows(tmp_path: Path) -> None:
    bundle = {
        "version": 1,
        "erpnext_version": "16.31.1",
        "documents": [
            {
                "doctype": "Workflow",
                "name": "Duyệt Đà Nẵng",
                "state": "present",
                "fields": {
                    "document_type": "Purchase Invoice",
                    "transitions": [{"state": "Nháp", "action": "Duyệt", "next_state": "Đã duyệt"}],
                },
            }
        ],
    }
    path = tmp_path / "policy.yaml"
    path.write_text(policy.dump_policy(bundle), encoding="utf-8")

    assert policy.load_policy(path) == bundle


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "version: 1\nversion: 1\nerpnext_version: 16.31.1\ndocuments: []\n",
            "Duplicate YAML key",
        ),
        (
            "version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Account\n    name: Cash\n    fields: {}\n",
            "unsupported DocType",
        ),
        (
            "version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Accounts Settings\n    name: Wrong\n    fields: {}\n",
            "must use name Accounts Settings",
        ),
        (
            "version: 1\nerpnext_version: 16.31.1\ndocuments:\n  - doctype: Role\n    name: Test\n    state: absent\n    fields: {disabled: 1}\n",
            "cannot define fields",
        ),
    ],
)
def test_invalid_policy_fails_closed(tmp_path: Path, body: str, message: str) -> None:
    path = write_policy(tmp_path / "invalid.yaml", body)

    with pytest.raises(policy.PolicyError, match=message):
        policy.load_policy(path)


def test_duplicate_policy_document_is_rejected(tmp_path: Path) -> None:
    path = write_policy(
        tmp_path / "duplicate.yaml",
        """version: 1
erpnext_version: 16.31.1
documents:
  - doctype: Role
    name: Accounts User
    fields: {}
  - doctype: Role
    name: Accounts User
    fields: {}
""",
    )

    with pytest.raises(policy.PolicyError, match="Duplicate policy document"):
        policy.load_policy(path)
