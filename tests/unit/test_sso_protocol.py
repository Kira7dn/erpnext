from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from letron_api.sso_protocol import (
    CALLBACK_PATH,
    build_authorization_url,
    desired_erp_roles,
    load_configuration,
    pkce_challenge,
)


def _environment() -> dict[str, str]:
    return {
        "LETRON_SSO_ISSUER": "http://localhost:3000/api/oidc/",
        "LETRON_SSO_INTERNAL_ISSUER": "http://host.docker.internal:3000/api/oidc/",
        "LETRON_SSO_CLIENT_ID": "letron-erp",
        "LETRON_SSO_CLIENT_SECRET": "x" * 43,
        "LETRON_SSO_ERP_BASE_URL": "http://localhost:8080/",
    }


def test_configuration_builds_exact_local_callback() -> None:
    config = load_configuration(_environment())

    assert config.redirect_uri == f"http://localhost:8080{CALLBACK_PATH}"
    assert config.token_url == "http://host.docker.internal:3000/api/oidc/token"


def test_authorization_url_requires_code_pkce_and_openid() -> None:
    config = load_configuration(_environment())
    url = build_authorization_url(config, state="state", nonce="nonce", verifier="v" * 64)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "http://localhost:3000/api/oidc/auth"
    assert query == {
        "client_id": ["letron-erp"],
        "response_type": ["code"],
        "redirect_uri": ["http://localhost:8080/api/method/letron_api.sso.callback"],
        "scope": ["openid profile email groups"],
        "state": ["state"],
        "nonce": ["nonce"],
        "code_challenge": [pkce_challenge("v" * 64)],
        "code_challenge_method": ["S256"],
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LETRON_SSO_ISSUER", "http://auth.example.com/api/oidc"),
        ("LETRON_SSO_ERP_BASE_URL", "https://erp.example.com/path?unexpected=1"),
        ("LETRON_SSO_CLIENT_SECRET", "short"),
    ],
)
def test_configuration_rejects_unsafe_or_invalid_values(name: str, value: str) -> None:
    environment = _environment()
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
