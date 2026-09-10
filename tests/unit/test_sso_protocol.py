from __future__ import annotations

import pytest
from letron_api.auth.sso_protocol import (
    desired_erp_roles,
    load_configuration,
)


def _environment() -> dict[str, str]:
    return {
        "LETRON_SSO_ROLE_SYNC_ENABLED": "false",
    }


def test_configuration_has_no_native_oidc_contract() -> None:
    config = load_configuration(_environment())

    assert config.role_sync.enabled is False
    assert not hasattr(config, "redirect_uri")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LETRON_SSO_SYNC_URL", "https://auth.example.com/path?unexpected=1"),
    ],
)
def test_configuration_rejects_unsafe_or_invalid_values(name: str, value: str) -> None:
    environment = _environment()
    environment["LETRON_SSO_ROLE_SYNC_ENABLED"] = "true"
    environment["LETRON_SSO_REQUIRED_LARK_GROUP_ID"] = "g-access"
    environment["LETRON_SSO_SYNC_SECRET"] = "s" * 32
    environment[name] = value

    with pytest.raises(ValueError):
        load_configuration(environment)


def test_lark_groups_project_only_deterministic_policy_roles() -> None:
    environment = _environment() | {
        "LETRON_SSO_ROLE_SYNC_ENABLED": "true",
        "LETRON_SSO_REQUIRED_LARK_GROUP_ID": "g-access",
        "LETRON_SSO_SYNC_URL": "http://host.docker.internal:3000/api/internal/lark-role-snapshots",
        "LETRON_SSO_SYNC_SECRET": "s" * 32,
    }
    role_sync = load_configuration(environment).role_sync

    assert role_sync.enabled is True
    assert role_sync.request_check_interval_seconds == 60
    assert role_sync.snapshot_max_age_seconds == 120
    assert role_sync.stale_lock_seconds == 600
    assert role_sync.break_glass_max_seconds == 3600
    assert desired_erp_roles({"g-access", "g-accounts", "unrelated"}, role_sync) == {
        "Letron Policy - group-g-access",
        "Letron Policy - group-g-accounts",
        "Letron Policy - group-unrelated",
    }


def test_role_sync_requires_access_group_and_internal_sync_credentials() -> None:
    environment = _environment() | {
        "LETRON_SSO_ROLE_SYNC_ENABLED": "true",
        "LETRON_SSO_REQUIRED_LARK_GROUP_ID": "g-access",
        "LETRON_SSO_SYNC_URL": "http://host.docker.internal:3000/api/internal/lark-role-snapshots",
        "LETRON_SSO_SYNC_SECRET": "s" * 32,
    }
    environment.pop("LETRON_SSO_SYNC_SECRET")
    with pytest.raises(ValueError, match="LETRON_SSO_SYNC_SECRET"):
        load_configuration(environment)


def test_role_sync_requires_stale_lock_to_exceed_login_snapshot_age() -> None:
    environment = _environment() | {
        "LETRON_SSO_ROLE_SYNC_ENABLED": "true",
        "LETRON_SSO_REQUIRED_LARK_GROUP_ID": "g-access",
        "LETRON_SSO_SYNC_URL": "http://host.docker.internal:3000/api/internal/lark-role-snapshots",
        "LETRON_SSO_SYNC_SECRET": "s" * 32,
        "LETRON_SSO_SNAPSHOT_MAX_AGE_SECONDS": "300",
        "LETRON_SSO_STALE_LOCK_SECONDS": "300",
    }

    with pytest.raises(ValueError, match="must exceed snapshot max age"):
        load_configuration(environment)


def test_role_sync_requires_request_check_interval_within_snapshot_age() -> None:
    environment = _environment() | {
        "LETRON_SSO_ROLE_SYNC_ENABLED": "true",
        "LETRON_SSO_REQUIRED_LARK_GROUP_ID": "g-access",
        "LETRON_SSO_SYNC_URL": "http://host.docker.internal:3000/api/internal/lark-role-snapshots",
        "LETRON_SSO_SYNC_SECRET": "s" * 32,
        "LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS": "121",
        "LETRON_SSO_SNAPSHOT_MAX_AGE_SECONDS": "120",
    }

    with pytest.raises(ValueError, match="must not exceed snapshot max age"):
        load_configuration(environment)
