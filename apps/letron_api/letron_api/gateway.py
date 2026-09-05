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
            "X-Letron-Gateway-Method",
            "X-Letron-Gateway-Path",
            "X-Letron-Gateway-User",
            "X-Letron-Gateway-Email",
            "X-Letron-Gateway-Policy-Version",
            "X-Letron-Gateway-Roles",
        )
    )


def verify_gateway_request() -> str:
    headers = frappe.local.request.headers
    secret = os.environ.get("LETRON_SSO_SYNC_SECRET", "")
    timestamp = headers.get("X-Letron-Gateway-Timestamp", "")
    signature = headers.get("X-Letron-Gateway-Signature", "")
    path = headers.get("X-Letron-Gateway-Path", "")
    if not secret or not timestamp or not signature or not path.startswith("/api/v1/"):
        frappe.throw("Gateway authorization required", exc=frappe.AuthenticationError)
    try:
        age = abs(time.time() - int(timestamp))
    except ValueError:
        frappe.throw("Invalid gateway timestamp", exc=frappe.AuthenticationError)
    if age > 60:
        frappe.throw("Expired gateway authorization", exc=frappe.AuthenticationError)
    expected = hmac.new(secret.encode(), _signature_payload(headers).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        frappe.throw("Invalid gateway authorization", exc=frappe.AuthenticationError)
    if headers.get("X-Letron-Gateway-Method", "") != frappe.local.request.method:
        frappe.throw("Gateway method mismatch", exc=frappe.AuthenticationError)
    email = headers.get("X-Letron-Gateway-Email", "").strip().lower()
    if not email:
        frappe.throw("Gateway identity missing", exc=frappe.AuthenticationError)
    user = frappe.db.get_value("User", {"email": email, "enabled": 1, "user_type": "System User"}, "name")
    if not user:
        frappe.throw("Gateway identity is not an active ERP user", exc=frappe.PermissionError)
    frappe.set_user(user)
    _sync_policy_roles(user, headers.get("X-Letron-Gateway-Roles", ""))
    frappe.local.letron_gateway_policy_version = headers.get("X-Letron-Gateway-Policy-Version", "")
    frappe.local.letron_gateway_user = user
    return user


def _sync_policy_roles(user: str, encoded_roles: str) -> None:
    """Project only policy-managed roles for this signed gateway identity."""
    try:
        padded = encoded_roles + "=" * (-len(encoded_roles) % 4)
        roles = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        frappe.throw("Invalid gateway roles", exc=frappe.AuthenticationError)
    if not isinstance(roles, list) or any(not isinstance(role, str) or not role.startswith("Letron Policy - ") for role in roles):
        frappe.throw("Invalid gateway roles", exc=frappe.AuthenticationError)
    desired = set(roles)
    user_doc = frappe.get_doc("User", user)
    current = {row.role for row in user_doc.roles}
    retained = [row for row in user_doc.roles if not row.role.startswith("Letron Policy - ") or row.role in desired]
    current_retained = {row.role for row in retained}
    for role in sorted(desired - current_retained):
        retained.append({"role": role})
    if {row.role for row in user_doc.roles} != {row.role for row in retained}:
        user_doc.set("roles", retained)
        user_doc.save(ignore_permissions=True)


def enforce_gateway_ingress() -> None:
    path = frappe.local.request.path
    if path.startswith("/api/v1/"):
        verify_gateway_request()
        frappe.local.letron_gateway_authorized = True
        return

    # Lark-linked users must use the Global Portal policy gateway for business
    # API traffic. Native Frappe API routes would otherwise bypass the
    # operation-level OpenAPI decision even when their ERP roles are projected
    # correctly. Keep the SSO launch/callback/logout methods available.
    native_api = path.startswith("/api/resource/") or path.startswith("/api/method/")
    sso_method = path in {
        "/api/method/letron_api.sso.launch",
        "/api/method/letron_api.sso.callback",
        "/api/method/frappe.auth.logout",
        "/api/method/logout",
    }
    user = getattr(frappe.session, "user", "Guest")
    if native_api and not sso_method and user not in {"", "Guest"} and frappe.db.table_exists("Letron SSO Identity"):
        if frappe.db.exists("Letron SSO Identity", {"user": user}):
            frappe.throw("Global Portal gateway required", exc=frappe.AuthenticationError)
