from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from typing import Any

import frappe


def _signature_payload(headers: Any) -> str:
    return ".".join(
        str(headers.get(name, ""))
        for name in (
            "X-Letron-Gateway-Timestamp",
            "X-Letron-Gateway-Expires-At",
            "X-Letron-Gateway-Method",
            "X-Letron-Gateway-Path",
            "X-Letron-Gateway-User",
            "X-Letron-Gateway-Email",
            "X-Letron-Gateway-Tenant",
            "X-Letron-Gateway-Subject",
            "X-Letron-Gateway-Subject-Type",
            "X-Letron-Gateway-Policy-Version",
            "X-Letron-Gateway-Roles",
            "X-Letron-Gateway-Request-Id",
        )
    )


def verify_gateway_request() -> str:
    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_SSO_SYNC_SECRET", "")
    timestamp = headers.get("X-Letron-Gateway-Issued-At", "") or headers.get("X-Letron-Gateway-Timestamp", "")
    expires_at = headers.get("X-Letron-Gateway-Expires-At", "")
    signature = headers.get("X-Letron-Gateway-Signature", "")
    path = headers.get("X-Letron-Gateway-Path", "")
    if not secret or not timestamp or not expires_at or not signature or not path.startswith("/api/v1/"):
        frappe.throw("Gateway authorization required", exc=frappe.AuthenticationError)
    try:
        issued_at = int(timestamp)
        expiry = int(expires_at)
        age = abs(time.time() - issued_at)
    except ValueError:
        frappe.throw("Invalid gateway timestamp", exc=frappe.AuthenticationError)
    if age > 60 or expiry < time.time() or expiry <= issued_at:
        frappe.throw("Expired gateway authorization", exc=frappe.AuthenticationError)
    expected = hmac.new(secret.encode(), _signature_payload(headers).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid gateway authorization", exc=frappe.AuthenticationError)
    if headers.get("X-Letron-Gateway-Method", "") != frappe.local.request.method:
        frappe.throw("Gateway method mismatch", exc=frappe.AuthenticationError)
    email = headers.get("X-Letron-Gateway-Email", "").strip().lower()
    tenant = headers.get("X-Letron-Gateway-Tenant", "").strip()
    subject = headers.get("X-Letron-Gateway-Subject", "").strip()
    subject_type = headers.get("X-Letron-Gateway-Subject-Type", "").strip()
    if not email or not tenant or not subject or subject_type != "union_id" or not headers.get("X-Letron-Gateway-User", "").strip() or not headers.get("X-Letron-Gateway-Request-Id", "").strip():
        frappe.throw("Gateway identity missing", exc=frappe.AuthenticationError)
    identity = frappe.db.get_value(
        "Letron SSO Identity",
        {"tenant_key": tenant, "subject": subject, "subject_type": subject_type},
        ["name", "user", "email", "sync_state", "local_blocked"],
        as_dict=True,
    ) if frappe.db.table_exists("Letron SSO Identity") else None
    user = identity.user if identity else None
    if not user or identity.email.lower() != email or identity.sync_state != "Active" or identity.local_blocked:
        frappe.throw("Gateway identity is not an active ERP identity", exc=frappe.PermissionError)
    active = frappe.db.get_value("User", {"name": user, "enabled": 1, "user_type": "System User"}, "name")
    if not active:
        frappe.throw("Gateway identity is not an active ERP user", exc=frappe.PermissionError)
    frappe.set_user(user)
    sync_gateway_roles_if_changed(user, identity.name, headers.get("X-Letron-Gateway-Roles", ""), headers.get("X-Letron-Gateway-Policy-Version", ""))
    frappe.local.letron_gateway_policy_version = headers.get("X-Letron-Gateway-Policy-Version", "")
    frappe.local.letron_gateway_user = user
    return user


def verify_control_plane_request() -> None:
    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_SSO_SYNC_SECRET", "")
    timestamp = headers.get("X-Letron-Control-Timestamp", "")
    expires_at = headers.get("X-Letron-Control-Expires-At", "")
    request_id = headers.get("X-Letron-Control-Request-Id", "")
    signature = headers.get("X-Letron-Control-Signature", "")
    path = "/api/method/letron_api.access_policy.publish"
    if not secret or not timestamp or not expires_at or not request_id or not signature:
        frappe.throw("Control-plane authorization required", exc=frappe.AuthenticationError)
    try:
        issued_at = int(timestamp)
        expiry = int(expires_at)
        age = abs(time.time() - issued_at)
    except ValueError:
        frappe.throw("Invalid control-plane timestamp", exc=frappe.AuthenticationError)
    if age > 60 or expiry < time.time() or expiry <= issued_at:
        frappe.throw("Expired control-plane authorization", exc=frappe.AuthenticationError)
    payload = f"{timestamp}.{expires_at}.POST.{path}.{request_id}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid control-plane authorization", exc=frappe.AuthenticationError)


def sync_gateway_roles_if_changed(user: str, identity_name: str, encoded_roles: str, policy_version: str) -> None:
    """Project only policy-managed roles for this signed gateway identity."""
    try:
        padded = encoded_roles + "=" * (-len(encoded_roles) % 4)
        roles = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        frappe.throw("Invalid gateway roles", exc=frappe.AuthenticationError)
    if not isinstance(roles, list) or any(not isinstance(role, str) or not role.startswith("Letron Policy - ") for role in roles):
        frappe.throw("Invalid gateway roles", exc=frappe.AuthenticationError)
    desired = set(roles)
    if not policy_version.isdigit() or int(policy_version) <= 0:
        frappe.throw("Invalid gateway policy version", exc=frappe.AuthenticationError)
    cache = frappe.cache()
    lock_key = f"letron:sso:gateway-role-sync:{identity_name}"
    with cache.lock(lock_key, timeout=15, blocking_timeout=15):
        _sync_gateway_roles_if_changed_locked(user, identity_name, desired, policy_version)


def _sync_gateway_roles_if_changed_locked(user: str, identity_name: str, desired: set[str], policy_version: str) -> None:
    fingerprint = hashlib.sha256(json.dumps(sorted(desired), separators=(",", ":")).encode("utf-8")).hexdigest()
    stored = frappe.db.get_value("Letron SSO Identity", identity_name, ["gateway_roles_fingerprint", "gateway_policy_version"], as_dict=True)
    if stored and stored.gateway_roles_fingerprint == fingerprint and str(stored.gateway_policy_version or "") == policy_version:
        return
    user_doc = frappe.get_doc("User", user)
    current = {row.role for row in user_doc.roles}
    retained = [row for row in user_doc.roles if not row.role.startswith("Letron Policy - ") or row.role in desired]
    current_retained = {row.role for row in retained}
    for role in sorted(desired - current_retained):
        retained.append({"role": role})
    if {row.role for row in user_doc.roles} != {row.role for row in retained}:
        user_doc.flags.lark_sso_sync = True
        user_doc.set("roles", retained)
        user_doc.save(ignore_permissions=True)
    frappe.db.set_value("Letron SSO Identity", identity_name, {
        "gateway_roles_fingerprint": fingerprint,
        "gateway_policy_version": int(policy_version),
        "gateway_synced_at": frappe.utils.now_datetime(),
    }, update_modified=False)


def enforce_gateway_ingress() -> None:
    path = frappe.local.request.path
    if path.startswith("/api/v1/"):
        verify_gateway_request()
        frappe.local.letron_gateway_authorized = True
        return

    # Native business APIs are never an authorization path. Global Portal is
    # the only caller that may reach /api/v1/* with signed claims.
    native_api = path.startswith("/api/resource/") or path.startswith("/api/method/")
    native_exemptions = {
        "/api/method/letron_api.api.health",
        "/api/method/letron_api.api.runtime_info",
        "/api/method/letron_api.api.runtime_snapshot",
        "/api/method/letron_api.access_policy.publish",
    }
    if native_api and path not in native_exemptions:
        frappe.throw("Global Portal gateway required", exc=frappe.AuthenticationError)
