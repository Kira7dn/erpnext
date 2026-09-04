from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

CALLBACK_PATH = "/api/method/letron_api.sso.callback"
LAUNCH_PATH = "/api/method/letron_api.sso.launch"
OIDC_SCOPES = "openid profile email groups"
FORBIDDEN_LARK_MANAGED_ROLES = {"Administrator", "All", "Guest", "System Manager"}


class SsoConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class RoleSyncConfiguration:
    enabled: bool
    group_role_mapping: Mapping[str, tuple[str, ...]]
    managed_roles: frozenset[str]
    required_group_id: str | None
    sync_url: str | None
    sync_secret: str | None
    request_check_interval_seconds: int
    snapshot_max_age_seconds: int
    stale_lock_seconds: int
    break_glass_max_seconds: int


@dataclass(frozen=True)
class SsoConfiguration:
    issuer: str
    internal_issuer: str
    client_id: str
    client_secret: str
    erp_base_url: str
    role_sync: RoleSyncConfiguration

    @property
    def authorize_url(self) -> str:
        return f"{self.issuer}/auth"

    @property
    def token_url(self) -> str:
        return f"{self.internal_issuer}/token"

    @property
    def userinfo_url(self) -> str:
        return f"{self.internal_issuer}/me"

    @property
    def jwks_url(self) -> str:
        return f"{self.internal_issuer}/jwks"

    @property
    def redirect_uri(self) -> str:
        return f"{self.erp_base_url}{CALLBACK_PATH}"

    @property
    def launch_url(self) -> str:
        return f"{self.erp_base_url}{LAUNCH_PATH}"


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


def _json_value(env: Mapping[str, str], name: str) -> object:
    try:
        return json.loads(_required(env, name))
    except json.JSONDecodeError as exc:
        raise SsoConfigurationError(f"{name} must contain valid JSON") from exc


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
    if not _enabled(env, "LETRON_SSO_ROLE_SYNC_ENABLED"):
        return RoleSyncConfiguration(False, {}, frozenset(), None, None, None, 60, 120, 600, 3600)

    raw_mapping = _json_value(env, "LETRON_SSO_LARK_ROLE_MAPPING")
    raw_managed_roles = _json_value(env, "LETRON_SSO_LARK_MANAGED_ROLES")
    if not isinstance(raw_mapping, dict) or not raw_mapping:
        raise SsoConfigurationError("LETRON_SSO_LARK_ROLE_MAPPING must be a non-empty JSON object")
    if not isinstance(raw_managed_roles, list) or not raw_managed_roles:
        raise SsoConfigurationError("LETRON_SSO_LARK_MANAGED_ROLES must be a non-empty JSON array")

    managed_roles = frozenset(
        role.strip() for role in raw_managed_roles if isinstance(role, str) and role.strip()
    )
    if len(managed_roles) != len(raw_managed_roles):
        raise SsoConfigurationError("LETRON_SSO_LARK_MANAGED_ROLES contains invalid or duplicate roles")
    forbidden = managed_roles & FORBIDDEN_LARK_MANAGED_ROLES
    if forbidden:
        raise SsoConfigurationError(f"Privileged or implicit roles cannot be managed from Lark: {sorted(forbidden)}")

    mapping: dict[str, tuple[str, ...]] = {}
    for group_id, roles in raw_mapping.items():
        if not isinstance(group_id, str) or not group_id.strip() or not isinstance(roles, list) or not roles:
            raise SsoConfigurationError("Each Lark group mapping must have a group ID and at least one ERP role")
        normalized_roles = tuple(role.strip() for role in roles if isinstance(role, str) and role.strip())
        if len(normalized_roles) != len(roles) or len(set(normalized_roles)) != len(normalized_roles):
            raise SsoConfigurationError(f"Invalid or duplicate ERP roles for Lark group {group_id}")
        if not set(normalized_roles) <= managed_roles:
            raise SsoConfigurationError(f"Lark group {group_id} maps outside LETRON_SSO_LARK_MANAGED_ROLES")
        mapping[group_id.strip()] = normalized_roles

    required_group_id = _required(env, "LETRON_SSO_REQUIRED_LARK_GROUP_ID")
    if required_group_id not in mapping:
        raise SsoConfigurationError("LETRON_SSO_REQUIRED_LARK_GROUP_ID must exist in the role mapping")
    sync_url = _required(env, "LETRON_SSO_SYNC_URL")
    sync_secret = _required(env, "LETRON_SSO_SYNC_SECRET")
    _validate_url("LETRON_SSO_SYNC_URL", sync_url, allow_internal_http=True)
    if len(sync_secret) < 32:
        raise SsoConfigurationError("LETRON_SSO_SYNC_SECRET must contain at least 32 characters")
    snapshot_max_age_seconds = _integer(env, "LETRON_SSO_SNAPSHOT_MAX_AGE_SECONDS", 120, 30, 600)
    request_check_interval_seconds = _integer(
        env,
        "LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS",
        60,
        15,
        600,
    )
    stale_lock_seconds = _integer(env, "LETRON_SSO_STALE_LOCK_SECONDS", 600, 60, 86400)
    break_glass_max_seconds = _integer(env, "LETRON_SSO_BREAK_GLASS_MAX_SECONDS", 3600, 60, 14400)
    if stale_lock_seconds <= snapshot_max_age_seconds:
        raise SsoConfigurationError("LETRON_SSO_STALE_LOCK_SECONDS must exceed snapshot max age")
    if request_check_interval_seconds > snapshot_max_age_seconds:
        raise SsoConfigurationError("LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS must not exceed snapshot max age")
    return RoleSyncConfiguration(
        True,
        mapping,
        managed_roles,
        required_group_id,
        sync_url,
        sync_secret,
        request_check_interval_seconds,
        snapshot_max_age_seconds,
        stale_lock_seconds,
        break_glass_max_seconds,
    )


def load_configuration(env: Mapping[str, str]) -> SsoConfiguration:
    config = SsoConfiguration(
        issuer=_required(env, "LETRON_SSO_ISSUER"),
        internal_issuer=_required(env, "LETRON_SSO_INTERNAL_ISSUER"),
        client_id=_required(env, "LETRON_SSO_CLIENT_ID"),
        client_secret=_required(env, "LETRON_SSO_CLIENT_SECRET"),
        erp_base_url=_required(env, "LETRON_SSO_ERP_BASE_URL"),
        role_sync=_load_role_sync_configuration(env),
    )
    _validate_url("LETRON_SSO_ISSUER", config.issuer)
    _validate_url("LETRON_SSO_INTERNAL_ISSUER", config.internal_issuer)
    _validate_url("LETRON_SSO_ERP_BASE_URL", config.erp_base_url)
    if len(config.client_secret) < 32:
        raise SsoConfigurationError("LETRON_SSO_CLIENT_SECRET must contain at least 32 characters")
    return config


def desired_erp_roles(group_ids: set[str], role_sync: RoleSyncConfiguration) -> set[str]:
    return {
        role
        for group_id in group_ids
        for role in role_sync.group_role_mapping.get(group_id, ())
    }


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_url(
    config: SsoConfiguration,
    *,
    state: str,
    nonce: str,
    verifier: str,
) -> str:
    query = urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": OIDC_SCOPES,
            "state": state,
            "nonce": nonce,
            "code_challenge": pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{config.authorize_url}?{query}"
