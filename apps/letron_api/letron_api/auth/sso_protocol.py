from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

POLICY_ROLE_PREFIX = "Letron Policy - "
FORBIDDEN_LARK_MANAGED_ROLES = {"Administrator", "All", "Guest", "System Manager"}
ROLE_SYNC_ENABLED = True
REQUEST_CHECK_INTERVAL_SECONDS = 60
SNAPSHOT_MAX_AGE_SECONDS = 120
STALE_LOCK_SECONDS = 600
BREAK_GLASS_MAX_SECONDS = 3600
REQUIRED_LARK_GROUP_ID = "8be4c17b6a1f837c"


class SsoConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RoleSyncConfiguration:
    enabled: bool
    required_group_id: str | None
    sync_url: str | None
    sync_secret: str | None
    request_check_interval_seconds: int
    snapshot_max_age_seconds: int
    stale_lock_seconds: int
    break_glass_max_seconds: int


@dataclass(frozen=True)
class SsoConfiguration:
    role_sync: RoleSyncConfiguration


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise SsoConfigurationError(f"Missing required environment variable: {name}")
    return value.rstrip("/") if name.endswith(("ISSUER", "BASE_URL")) else value


def _validate_url(name: str, value: str, *, allow_internal_http: bool = False) -> None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc or parsed.query or parsed.fragment:
        raise SsoConfigurationError(f"{name} must be an absolute URL without query or fragment")
    local_hosts = {"localhost", "127.0.0.1", "host.docker.internal"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and (parsed.hostname in local_hosts or allow_internal_http)
    ):
        raise SsoConfigurationError(f"{name} must use HTTPS except for local development")


def _enabled(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name, "false").strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"", "0", "false", "no", "off"}:
        return False
    raise SsoConfigurationError(f"{name} must be true or false")


def _integer(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SsoConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise SsoConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _load_role_sync_configuration(env: Mapping[str, str]) -> RoleSyncConfiguration:
    required_group_id = REQUIRED_LARK_GROUP_ID
    auth_base_url = _required(env, "LETRON_AUTH_BASE_URL")
    sync_url = f"{auth_base_url}/api/internal/lark-role-snapshots"
    sync_secret = _required(env, "LETRON_INTERNAL_API_SECRET")
    _validate_url("LETRON_AUTH_BASE_URL", auth_base_url, allow_internal_http=True)
    if len(sync_secret) < 32:
        raise SsoConfigurationError("LETRON_INTERNAL_API_SECRET must contain at least 32 characters")
    snapshot_max_age_seconds = SNAPSHOT_MAX_AGE_SECONDS
    request_check_interval_seconds = REQUEST_CHECK_INTERVAL_SECONDS
    stale_lock_seconds = STALE_LOCK_SECONDS
    break_glass_max_seconds = BREAK_GLASS_MAX_SECONDS
    if stale_lock_seconds <= snapshot_max_age_seconds:
        raise SsoConfigurationError("stale lock duration must exceed snapshot max age")
    if request_check_interval_seconds > snapshot_max_age_seconds:
        raise SsoConfigurationError("request check interval must not exceed snapshot max age")
    return RoleSyncConfiguration(
        True,
        required_group_id,
        sync_url,
        sync_secret,
        request_check_interval_seconds,
        snapshot_max_age_seconds,
        stale_lock_seconds,
        break_glass_max_seconds,
    )


def load_configuration(env: Mapping[str, str]) -> SsoConfiguration:
    return SsoConfiguration(role_sync=_load_role_sync_configuration(env))


def desired_erp_roles(group_ids: set[str], role_sync: RoleSyncConfiguration) -> set[str]:
    # The group remains the role identity. The Portal owns permissions for the
    # deterministic technical role; ERP only assigns that role to the linked
    # user so Frappe can enforce the projected Custom DocPerm rows.
    return {
        f"{POLICY_ROLE_PREFIX}group-{re.sub(r'[^a-z0-9]+', '-', group_id.lower()).strip('-')}"
        for group_id in group_ids
        if re.sub(r"[^a-z0-9]+", "-", group_id.lower()).strip("-")
    }


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
