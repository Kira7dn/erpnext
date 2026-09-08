from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import frappe

from letron_api.sso_protocol import FORBIDDEN_LARK_MANAGED_ROLES, POLICY_ROLE_PREFIX, RoleSyncConfiguration, desired_erp_roles, sha256_hex

IDENTITY_DOCTYPE = "Letron SSO Identity"
AUDIT_DOCTYPE = "Letron SSO Audit Log"
IDENTITY_SYNC_FIELDS = (
    "identity_key",
    "provider",
    "tenant_key",
    "subject",
    "subject_type",
    "user",
    "email",
    "display_name",
    "group_ids",
    "last_sync_at",
    "gateway_roles_fingerprint",
    "gateway_policy_version",
    "gateway_synced_at",
    "sync_state",
    "disabled_by_sync",
    "local_blocked",
    "last_error",
    "break_glass_until",
    "break_glass_reason",
)
LEGACY_NATIVE_ROLES = frozenset({
    "Desk User", "Accounts User", "Accounts Manager", "Purchase User", "Purchase Manager",
    "Stock User", "Stock Manager", "Sales User", "Sales Manager",
})


def _managed_policy_roles(roles: set[str]) -> set[str]:
    return {role for role in roles if role.startswith(POLICY_ROLE_PREFIX)}


class SsoIdentityError(ValueError):
    pass


class SsoAccessDenied(SsoIdentityError):
    pass


class SsoIdentityConflict(SsoIdentityError):
    pass


class SsoSnapshotStale(SsoIdentityError):
    pass


@dataclass(frozen=True)
class IdentitySnapshot:
    tenant_key: str
    subject: str
    subject_type: str
    email: str
    display_name: str
    groups: frozenset[str]
    synced_at: datetime

    @property
    def identity_key(self) -> str:
        return sha256_hex(f"lark\0{self.tenant_key}\0{self.subject}")


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SsoIdentityError(f"Missing or invalid identity field: {field}")
    return value.strip()


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SsoIdentityError("Missing group snapshot timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SsoIdentityError("Invalid group snapshot timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _frappe_datetime(value: datetime) -> datetime:
    """Store an instant in Frappe's timezone-naive MariaDB Datetime columns."""

    return frappe.utils.convert_utc_to_system_timezone(value).replace(tzinfo=None)


def snapshot_from_payload(payload: dict[str, Any], *, max_age_seconds: int | None = None) -> IdentitySnapshot:
    groups = payload.get("groups")
    if not isinstance(groups, list) or any(not isinstance(group, str) or not group for group in groups):
        raise SsoIdentityError("Invalid Lark group snapshot")
    subject_type = _required_string(payload, "lark_subject_type" if "lark_subject_type" in payload else "subject_type")
    if subject_type != "union_id":
        raise SsoIdentityError("Stable Lark union_id is required")
    synced_at = _parse_timestamp(payload.get("lark_groups_synced_at", payload.get("groups_synced_at")))
    if max_age_seconds is not None:
        age = (datetime.now(UTC) - synced_at).total_seconds()
        if age < -60 or age > max_age_seconds:
            raise SsoSnapshotStale("Lark group snapshot is stale")
    return IdentitySnapshot(
        tenant_key=_required_string(payload, "lark_tenant_key" if "lark_tenant_key" in payload else "tenant_key"),
        subject=_required_string(payload, "lark_subject" if "lark_subject" in payload else "subject"),
        subject_type=subject_type,
        email=_required_string(payload, "email").lower(),
        display_name=_required_string(payload, "name" if "name" in payload else "display_name"),
        groups=frozenset(groups),
        synced_at=synced_at,
    )


def _json_list(values: set[str] | frozenset[str]) -> str:
    return json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":"))


def _audit(
    event_type: str,
    *,
    source: str,
    outcome: str,
    identity: str | None = None,
    user: str | None = None,
    before_roles: set[str] | None = None,
    after_roles: set[str] | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    document = frappe.get_doc(
        {
            "doctype": AUDIT_DOCTYPE,
            "occurred_at": _frappe_datetime(datetime.now(UTC)),
            "event_type": event_type,
            "identity": identity,
            "user": user,
            "source": source,
            "outcome": outcome,
            "before_roles": _json_list(before_roles or set()),
            "after_roles": _json_list(after_roles or set()),
            "detail": json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
        }
    )
    document.insert(ignore_permissions=True)


def _identity(name: str) -> Any | None:
    return frappe.get_doc(IDENTITY_DOCTYPE, name) if frappe.db.exists(IDENTITY_DOCTYPE, name) else None


def _save(document: Any) -> None:
    if document.is_new():
        document.insert(ignore_permissions=True)
    else:
        # SSO identity rows are refreshed by concurrent authenticated requests.
        # Document.save() performs an optimistic modified-timestamp check and
        # turns that expected race into MariaDB error 1020. These fields are
        # server-maintained state with no document hooks, so update them in one
        # direct statement and keep the in-memory document current.
        values = {fieldname: document.get(fieldname) for fieldname in IDENTITY_SYNC_FIELDS}
        frappe.db.set_value(IDENTITY_DOCTYPE, document.name, values, update_modified=True)
        document.reload()


def _clear_sessions(user_name: str) -> None:
    from frappe.sessions import clear_sessions

    clear_sessions(user=user_name, keep_current=False, force=True)


def _break_glass_active(identity: Any) -> bool:
    if not identity.break_glass_until:
        return False
    return frappe.utils.get_datetime(identity.break_glass_until) > frappe.utils.now_datetime()


def _sync_user(
    user: Any,
    *,
    desired_roles: set[str],
    managed_roles: frozenset[str],
    enabled: bool,
) -> tuple[set[str], set[str]]:
    before = {row.role for row in user.roles}
    after = (before - managed_roles) | desired_roles
    target_enabled = 1 if enabled else 0
    target_user_type = "System User" if enabled else "Website User"
    if before == after and int(user.enabled) == target_enabled and user.user_type == target_user_type:
        return before, after
    user.flags.lark_sso_sync = True
    user.enabled = target_enabled
    user.user_type = target_user_type
    user.set("roles", [])
    for role in sorted(after):
        user.append("roles", {"role": role})
    user.save(ignore_permissions=True)
    # Frappe derives user_type from desk-access roles during User.save().
    # Policy roles are intentionally API roles and may not grant Desk access,
    # but the public gateway still requires an active System User.
    frappe.db.set_value("User", user.name, "user_type", target_user_type, update_modified=False)
    frappe.clear_cache(user=user.name)
    return before, after


def _create_user(snapshot: IdentitySnapshot, desired_roles: set[str]) -> Any:
    if frappe.db.exists("User", snapshot.email):
        raise SsoIdentityConflict("Email already belongs to an unlinked ERP user")
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": snapshot.email,
            "first_name": snapshot.display_name,
            "enabled": 1,
            "send_welcome_email": 0,
            "new_password": frappe.generate_hash(length=32),
            "roles": [{"role": role} for role in sorted(desired_roles)],
        }
    )
    user.flags.lark_sso_sync = True
    user.flags.no_welcome_mail = True
    user.insert(ignore_permissions=True)
    return user


def _update_profile(identity: Any, user: Any, snapshot: IdentitySnapshot) -> Any:
    if user.name != snapshot.email:
        if frappe.db.exists("User", snapshot.email):
            raise SsoIdentityConflict("New Lark email already belongs to another ERP user")
        from frappe.model.rename_doc import rename_doc

        user.flags.lark_sso_sync = True
        rename_doc(
            "User",
            user.name,
            snapshot.email,
            force=False,
            merge=False,
            ignore_permissions=True,
            show_alert=False,
        )
        user = frappe.get_doc("User", snapshot.email)
        identity.reload()
    if user.first_name != snapshot.display_name:
        user.flags.lark_sso_sync = True
        user.first_name = snapshot.display_name
        user.save(ignore_permissions=True)
    return user


def reconcile_identity(
    snapshot: IdentitySnapshot,
    role_sync: RoleSyncConfiguration,
    *,
    source: str,
    allow_create: bool,
) -> str:
    identity = _identity(snapshot.identity_key)
    has_access = role_sync.required_group_id in snapshot.groups
    desired_roles = desired_erp_roles(set(snapshot.groups), role_sync) if has_access else set()

    if identity is None:
        if not has_access:
            raise SsoAccessDenied("Lark identity is not in the ERP access group")
        if not allow_create:
            raise SsoIdentityConflict("Lark identity is not linked to an ERP user")
        user = _create_user(snapshot, desired_roles)
        identity = frappe.get_doc(
            {
                "doctype": IDENTITY_DOCTYPE,
                "identity_key": snapshot.identity_key,
                "provider": "lark",
                "tenant_key": snapshot.tenant_key,
                "subject": snapshot.subject,
                "subject_type": snapshot.subject_type,
                "user": user.name,
                "email": snapshot.email,
                "display_name": snapshot.display_name,
                "group_ids": _json_list(snapshot.groups),
                "last_sync_at": _frappe_datetime(snapshot.synced_at),
                "sync_state": "Active",
            }
        )
        _save(identity)
        _audit(
            "user.created",
            source=source,
            outcome="success",
            identity=identity.name,
            user=user.name,
            after_roles=desired_roles,
        )
        return user.name

    user = frappe.get_doc("User", identity.user)
    try:
        user = _update_profile(identity, user, snapshot)
    except SsoIdentityConflict as error:
        identity.sync_state = "Conflict"
        identity.last_error = str(error)
        _save(identity)
        _audit("identity.conflict", source=source, outcome="error", identity=identity.name, user=user.name)
        raise

    identity.email = snapshot.email
    identity.display_name = snapshot.display_name
    identity.subject_type = snapshot.subject_type
    identity.group_ids = _json_list(snapshot.groups)
    identity.last_sync_at = _frappe_datetime(snapshot.synced_at)
    identity.last_error = None

    if not has_access:
        was_enabled = bool(user.enabled)
        previous_state = identity.sync_state
        before, after = _sync_user(
            user,
            desired_roles=set(),
            managed_roles=LEGACY_NATIVE_ROLES | _managed_policy_roles(before),
            enabled=False,
        )
        identity.disabled_by_sync = 1
        identity.sync_state = "Access Removed"
        identity.break_glass_until = None
        identity.break_glass_reason = None
        _save(identity)
        if was_enabled or before != after or previous_state != "Access Removed":
            _clear_sessions(user.name)
            _audit(
                "access.removed",
                source=source,
                outcome="success",
                identity=identity.name,
                user=user.name,
                before_roles=before,
                after_roles=after,
            )
        raise SsoAccessDenied("Lark identity is not in the ERP access group")

    if identity.local_blocked or (not user.enabled and not identity.disabled_by_sync):
        identity.local_blocked = 1
        identity.sync_state = "Local Blocked"
        _save(identity)
        raise SsoAccessDenied("ERP user is locally blocked")

    if _break_glass_active(identity):
        identity.sync_state = "Active"
        identity.last_error = None
        _save(identity)
        return user.name

    was_enabled = bool(user.enabled)
    existing_roles = {row.role for row in user.roles}
    before, after = _sync_user(
        user,
        desired_roles=desired_roles,
        managed_roles=LEGACY_NATIVE_ROLES | _managed_policy_roles(existing_roles),
        enabled=True,
    )
    identity.user = user.name
    identity.disabled_by_sync = 0
    identity.sync_state = "Active"
    identity.break_glass_until = None
    identity.break_glass_reason = None
    _save(identity)
    if before != after or not was_enabled:
        _audit(
            "roles.reconciled",
            source=source,
            outcome="success",
            identity=identity.name,
            user=user.name,
            before_roles=before,
            after_roles=after,
        )
    return user.name


def link_existing_user(snapshot: IdentitySnapshot, user_name: str, role_sync: RoleSyncConfiguration) -> str:
    if _identity(snapshot.identity_key):
        return reconcile_identity(snapshot, role_sync, source="migration", allow_create=False)
    user = frappe.get_doc("User", user_name)
    if user.name.lower() != snapshot.email or not user.enabled or user.user_type != "System User":
        raise SsoIdentityConflict("Existing ERP user is not an active exact-email System User")
    competing = frappe.db.get_value(IDENTITY_DOCTYPE, {"user": user.name}, "name")
    if competing:
        raise SsoIdentityConflict("ERP user is already linked to another external identity")
    identity = frappe.get_doc(
        {
            "doctype": IDENTITY_DOCTYPE,
            "identity_key": snapshot.identity_key,
            "provider": "lark",
            "tenant_key": snapshot.tenant_key,
            "subject": snapshot.subject,
            "subject_type": snapshot.subject_type,
            "user": user.name,
            "email": snapshot.email,
            "display_name": snapshot.display_name,
            "group_ids": _json_list(snapshot.groups),
            "last_sync_at": _frappe_datetime(snapshot.synced_at),
            "sync_state": "Active",
        }
    )
    _save(identity)
    _audit("identity.backfilled", source="migration", outcome="success", identity=identity.name, user=user.name)
    return reconcile_identity(snapshot, role_sync, source="migration", allow_create=False)


def apply_break_glass(
    user_name: str,
    roles: set[str],
    reason: str,
    ttl_seconds: int,
    role_sync: RoleSyncConfiguration,
) -> dict[str, Any]:
    if any(role in FORBIDDEN_LARK_MANAGED_ROLES or not role.startswith(POLICY_ROLE_PREFIX) for role in roles):
        raise SsoIdentityError("Break-glass roles must be Global Portal policy roles")
    if not 60 <= ttl_seconds <= role_sync.break_glass_max_seconds:
        raise SsoIdentityError("Break-glass TTL is outside the configured range")
    identity_name = frappe.db.get_value(IDENTITY_DOCTYPE, {"user": user_name}, "name")
    if not identity_name:
        raise SsoIdentityError("ERP user is not linked to Lark")
    identity = frappe.get_doc(IDENTITY_DOCTYPE, identity_name)
    groups = set(json.loads(identity.group_ids or "[]"))
    if role_sync.required_group_id not in groups or identity.local_blocked:
        raise SsoAccessDenied("Break-glass cannot bypass ERP access removal or a local block")
    user = frappe.get_doc("User", user_name)
    before = {row.role for row in user.roles}
    before_managed = LEGACY_NATIVE_ROLES | _managed_policy_roles(before)
    before, after = _sync_user(user, desired_roles=roles, managed_roles=before_managed, enabled=True)
    identity.break_glass_until = frappe.utils.add_to_date(
        frappe.utils.now_datetime(), seconds=ttl_seconds, as_datetime=True
    )
    identity.break_glass_reason = reason[:140]
    identity.sync_state = "Active"
    _save(identity)
    _audit(
        "roles.break_glass",
        source="break-glass",
        outcome="success",
        identity=identity.name,
        user=user.name,
        before_roles=before,
        after_roles=after,
        detail={"reason": reason, "ttl_seconds": ttl_seconds},
    )
    return {"user": user.name, "roles": sorted(after), "break_glass_until": str(identity.break_glass_until)}


def record_sync_error(
    identity_key: str,
    error_code: str,
    role_sync: RoleSyncConfiguration,
    *,
    source: str = "request",
) -> None:
    identity = _identity(identity_key)
    if identity is None:
        return
    identity.last_error = error_code[:140]
    last_sync = frappe.utils.get_datetime(identity.last_sync_at) if identity.last_sync_at else None
    stale = last_sync is None or (
        frappe.utils.now_datetime() - last_sync
    ).total_seconds() >= role_sync.stale_lock_seconds
    if stale:
        transitioned = identity.sync_state != "Stale Locked"
        identity.sync_state = "Stale Locked"
        identity.disabled_by_sync = 1
        if transitioned:
            user = frappe.get_doc("User", identity.user)
            current_roles = {row.role for row in user.roles}
            _sync_user(
                user,
                desired_roles=current_roles & _managed_policy_roles(current_roles),
                managed_roles=LEGACY_NATIVE_ROLES | _managed_policy_roles(current_roles),
                enabled=False,
            )
            _clear_sessions(identity.user)
            _audit(
                "snapshot.stale_locked",
                source=source,
                outcome="denied",
                identity=identity.name,
                user=identity.user,
                detail={"error_code": error_code},
            )
    _save(identity)


def protect_lark_managed_user(document: Any, _method: str | None = None) -> None:
    if document.is_new() or getattr(document.flags, "lark_sso_sync", False):
        return
    identity_name = frappe.db.get_value(IDENTITY_DOCTYPE, {"user": document.name}, "name")
    if not identity_name:
        return
    import os

    from letron_api.sso_protocol import load_configuration

    role_sync = load_configuration(os.environ).role_sync
    previous_roles = set(frappe.get_all("Has Role", filters={"parent": document.name}, pluck="role"))
    next_roles = {row.role for row in document.roles}
    managed_before = LEGACY_NATIVE_ROLES | _managed_policy_roles(previous_roles)
    managed_after = LEGACY_NATIVE_ROLES | _managed_policy_roles(next_roles)
    if (previous_roles & managed_before) != (next_roles & managed_after):
        frappe.throw(
            "Managed ERP roles are controlled by Lark. Use the SSO break-glass command for a temporary override.",
            exc=frappe.PermissionError,
        )
    previous_enabled = bool(frappe.db.get_value("User", document.name, "enabled"))
    if previous_enabled and not document.enabled:
        frappe.db.set_value(
            IDENTITY_DOCTYPE,
            identity_name,
            {"local_blocked": 1, "sync_state": "Local Blocked"},
            update_modified=False,
        )
    elif not previous_enabled and document.enabled:
        disabled_by_sync = bool(frappe.db.get_value(IDENTITY_DOCTYPE, identity_name, "disabled_by_sync"))
        if disabled_by_sync:
            frappe.throw("A Lark-managed access removal cannot be bypassed by enabling the ERP user.", exc=frappe.PermissionError)
        frappe.db.set_value(
            IDENTITY_DOCTYPE,
            identity_name,
            {"local_blocked": 0, "sync_state": "Active"},
            update_modified=False,
        )


def status() -> dict[str, Any]:
    enabled = os.environ.get("LETRON_SSO_ROLE_SYNC_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return {"enabled": False}
    if not frappe.db.table_exists(IDENTITY_DOCTYPE):
        return {"enabled": True, "installed": False}
    counts = dict(Counter(frappe.get_all(IDENTITY_DOCTYPE, pluck="sync_state")))
    latest_rows = frappe.get_all(
        IDENTITY_DOCTYPE,
        fields=["last_sync_at"],
        filters={"last_sync_at": ["is", "set"]},
        order_by="last_sync_at desc",
        limit=1,
    )
    latest = latest_rows[0].last_sync_at if latest_rows else None
    return {
        "enabled": True,
        "installed": True,
        "identities": sum(counts.values()),
        "states": counts,
        "last_successful_sync_at": str(latest) if latest else None,
    }
