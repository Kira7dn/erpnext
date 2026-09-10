from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import frappe

from letron_api.auth.sso_identity import (
    MANAGED_NATIVE_ROLES,
    _managed_policy_roles,
    IdentitySnapshot,
    SsoAccessDenied,
    apply_break_glass,
    reconcile_identity,
    record_sync_error,
)
from letron_api.auth.sso_protocol import load_configuration


def _environment_list(csv_name: str, json_name: str) -> list[str]:
    csv_value = os.environ.get(csv_name, "")
    if csv_value.strip():
        return [item.strip() for item in csv_value.split(",") if item.strip()]
    value = json.loads(os.environ.get(json_name, "[]"))
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{json_name} must be a JSON array of non-empty strings")
    return [item.strip() for item in value]


def break_glass_from_environment() -> dict[str, object]:
    """Apply a bounded managed-role override without exposing a web route."""

    user = os.environ.get("LETRON_BREAK_GLASS_USER", "").strip().lower()
    reason = os.environ.get("LETRON_BREAK_GLASS_REASON", "").strip()
    roles = set(_environment_list("LETRON_BREAK_GLASS_ROLE_NAMES", "LETRON_BREAK_GLASS_ROLES"))
    ttl_seconds = int(os.environ.get("LETRON_BREAK_GLASS_TTL_SECONDS", "0"))
    if not user or not reason:
        raise ValueError("LETRON_BREAK_GLASS_USER and LETRON_BREAK_GLASS_REASON are required")
    result = apply_break_glass(user, roles, reason, ttl_seconds, load_configuration(os.environ).role_sync)
    frappe.db.commit()
    return result


def run_lark_sso_acceptance() -> dict[str, object]:
    """Exercise the Lark-owned lifecycle in one rollback-only transaction."""

    role_sync = load_configuration(os.environ).role_sync
    if not role_sync.enabled or not role_sync.required_group_id:
        raise ValueError("Lark role synchronization must be enabled")

    token = frappe.generate_hash(length=10).lower()
    email = f"sso-accept-{token}@example.invalid"
    renamed_email = f"sso-renamed-{token}@example.invalid"
    now = datetime.now(UTC)

    def snapshot(*, groups: frozenset[str], address: str = email, seconds: int = 0) -> IdentitySnapshot:
        return IdentitySnapshot(
            tenant_key=f"acceptance-tenant-{token}",
            subject=f"acceptance-union-{token}",
            subject_type="union_id",
            email=address,
            display_name="Letron SSO Acceptance",
            groups=groups,
            synced_at=now + timedelta(seconds=seconds),
        )

    access_snapshot = snapshot(groups=frozenset({role_sync.required_group_id}))
    checks: list[str] = []
    try:
        user_name = reconcile_identity(access_snapshot, role_sync, source="login", allow_create=True)
        user = cast(Any, frappe.get_doc("User", user_name))
        assert user.enabled and user.user_type == "System User"
        checks.append("jit_create")

        user.add_roles("Stock User")
        reconcile_identity(access_snapshot, role_sync, source="acceptance", allow_create=False)
        user = cast(Any, frappe.get_doc("User", user_name))
        assert "Stock User" in {row.role for row in user.roles}
        checks.append("unmanaged_role_preserved")

        managed_roles = MANAGED_NATIVE_ROLES | _managed_policy_roles({row.role for row in user.roles})
        user.set("roles", [row for row in user.roles if row.role not in managed_roles])
        try:
            user.save(ignore_permissions=True)
        except frappe.PermissionError:
            checks.append("managed_role_guard")
        else:
            raise AssertionError("Direct managed-role edit was not blocked")

        apply_break_glass(user_name, set(), "runtime acceptance", 60, role_sync)
        reconcile_identity(access_snapshot, role_sync, source="acceptance", allow_create=False)
        user = cast(Any, frappe.get_doc("User", user_name))
        assert not ({row.role for row in user.roles} & managed_roles)
        checks.append("break_glass_bounded")

        removed_snapshot = snapshot(groups=frozenset(), seconds=1)
        try:
            reconcile_identity(removed_snapshot, role_sync, source="acceptance", allow_create=False)
        except SsoAccessDenied:
            pass
        else:
            raise AssertionError("Access removal was not enforced")
        user = cast(Any, frappe.get_doc("User", user_name))
        assert not user.enabled and "Stock User" in {row.role for row in user.roles}
        checks.append("access_removed")

        restored_snapshot = snapshot(groups=access_snapshot.groups, seconds=2)
        reconcile_identity(restored_snapshot, role_sync, source="acceptance", allow_create=False)
        user = cast(Any, frappe.get_doc("User", user_name))
        assert user.enabled and "Stock User" in {row.role for row in user.roles}
        checks.append("access_restored")

        renamed_snapshot = snapshot(groups=access_snapshot.groups, address=renamed_email, seconds=3)
        user_name = reconcile_identity(renamed_snapshot, role_sync, source="acceptance", allow_create=False)
        assert user_name == renamed_email and not frappe.db.exists("User", email)
        checks.append("email_renamed_by_stable_identity")

        identity: Any = frappe.get_doc("Letron SSO Identity", renamed_snapshot.identity_key)
        identity.last_sync_at = frappe.utils.add_to_date(
            frappe.utils.now_datetime(),
            seconds=-(role_sync.stale_lock_seconds + 1),
            as_datetime=True,
        )
        identity.save(ignore_permissions=True)
        record_sync_error(
            renamed_snapshot.identity_key,
            "acceptance_endpoint_failure",
            role_sync,
            source="acceptance",
        )
        identity.reload()
        user = cast(Any, frappe.get_doc("User", user_name))
        assert identity.sync_state == "Stale Locked" and not user.enabled
        checks.append("stale_lock")

        fresh_snapshot = snapshot(groups=access_snapshot.groups, address=renamed_email, seconds=4)
        reconcile_identity(fresh_snapshot, role_sync, source="login", allow_create=False)
        user = cast(Any, frappe.get_doc("User", user_name))
        assert user.enabled
        checks.append("fresh_snapshot_unlock")

        user.enabled = 0
        user.save(ignore_permissions=True)
        try:
            reconcile_identity(fresh_snapshot, role_sync, source="login", allow_create=False)
        except SsoAccessDenied:
            checks.append("local_block_preserved")
        else:
            raise AssertionError("Local ERP block was not preserved")

        user = cast(Any, frappe.get_doc("User", user_name))
        user.enabled = 1
        user.save(ignore_permissions=True)
        reconcile_identity(fresh_snapshot, role_sync, source="login", allow_create=False)
        checks.append("local_admin_unblock")

        return {"ok": True, "checks": checks, "rolled_back": True}
    finally:
        frappe.db.rollback()
        frappe.clear_cache(user=email)
        frappe.clear_cache(user=renamed_email)
