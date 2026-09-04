from __future__ import annotations

import hmac
import json
import os
import secrets
from typing import Any, cast

import frappe
import jwt
import requests

from letron_api.sso_identity import (
    SsoAccessDenied,
    SsoIdentityConflict,
    SsoIdentityError,
    SsoSnapshotStale,
    reconcile_identity,
    record_sync_error,
    snapshot_from_payload,
)
from letron_api.sso_protocol import (
    build_authorization_url,
    load_configuration,
    sha256_hex,
)

TRANSACTION_PREFIX = "letron_sso_transaction"
BINDING_COOKIE = "letron_sso_binding"
TRANSACTION_TTL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10
SYNC_HTTP_TIMEOUT_SECONDS = 30


def _redirect(location: str) -> None:
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = location


def _error(title: str, message: str, status: int = 400) -> None:
    frappe.respond_as_web_page(
        title,
        message,
        success=False,
        http_status_code=status,
        primary_action="/login",
        primary_label="Quay lại đăng nhập",
        fullpage=True,
    )


def _transaction_key(state: str) -> str:
    return f"{TRANSACTION_PREFIX}:{sha256_hex(state)}"


def _consume_transaction(state: str) -> dict[str, str] | None:
    key = _transaction_key(state)
    cache = cast(Any, frappe.cache)
    with cache.lock(f"{key}:lock", timeout=5, blocking_timeout=5):
        value = cache.get_value(key, use_local_cache=False)
        cache.delete_value(key)
    return value if isinstance(value, dict) else None


def _decode_id_token(id_token: str, config: Any, expected_nonce: str) -> dict[str, Any]:
    header = jwt.get_unverified_header(id_token)
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise ValueError("Unsupported ID token signing metadata")
    response = requests.get(config.jwks_url, timeout=HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    keys = response.json().get("keys", [])
    jwk = next((item for item in keys if item.get("kid") == header["kid"]), None)
    if not jwk:
        raise ValueError("ID token signing key was not found")
    signing_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    claims = jwt.decode(
        id_token,
        signing_key,
        algorithms=["RS256"],
        audience=config.client_id,
        issuer=config.issuer,
        options={"require": ["exp", "iat", "iss", "sub", "aud", "nonce"]},
    )
    if not hmac.compare_digest(str(claims.get("nonce", "")), expected_nonce):
        raise ValueError("ID token nonce did not match")
    return claims


def _exchange_code(code: str, transaction: dict[str, str], config: Any) -> dict[str, Any]:
    token_response = requests.post(
        config.token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "code_verifier": transaction["verifier"],
        },
        auth=(config.client_id, config.client_secret),
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    token_response.raise_for_status()
    tokens = token_response.json()
    access_token = tokens.get("access_token")
    id_token = tokens.get("id_token")
    if not isinstance(access_token, str) or not isinstance(id_token, str):
        raise TypeError("OIDC token response is incomplete")

    id_claims = _decode_id_token(id_token, config, transaction["nonce"])
    userinfo_response = requests.get(
        config.userinfo_url,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    userinfo_response.raise_for_status()
    userinfo = userinfo_response.json()
    if userinfo.get("sub") != id_claims.get("sub"):
        raise ValueError("UserInfo subject did not match the ID token")
    if userinfo.get("email_verified") is not True:
        raise ValueError("The identity provider did not verify the email address")
    return userinfo


def _authorized_erp_user(email: str) -> str | None:
    user = frappe.db.get_value(
        "User",
        {"email": email.strip().lower()},
        ["name", "enabled", "user_type"],
        as_dict=True,
    )
    if not user or not user.enabled or user.user_type != "System User":
        return None
    return str(user.name)


@frappe.whitelist(allow_guest=True)
def launch() -> None:
    if frappe.session.user not in {"", "Guest"}:
        _redirect("/desk")
        return

    try:
        config = load_configuration(os.environ)
    except ValueError:
        _error("SSO chưa được cấu hình", "Quản trị viên cần hoàn tất cấu hình Letron SSO.", 503)
        return

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    browser_binding = secrets.token_urlsafe(32)
    cast(Any, frappe.cache).set_value(
        _transaction_key(state),
        {
            "nonce": nonce,
            "verifier": verifier,
            "binding_hash": sha256_hex(browser_binding),
        },
        expires_in_sec=TRANSACTION_TTL_SECONDS,
    )
    frappe.local.cookie_manager.set_cookie(
        BINDING_COOKIE,
        browser_binding,
        max_age=TRANSACTION_TTL_SECONDS,
        httponly=True,
        samesite="Lax",
    )
    _redirect(build_authorization_url(config, state=state, nonce=nonce, verifier=verifier))


@frappe.whitelist(allow_guest=True)
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> None:
    if error:
        _error("Đăng nhập bị hủy", error_description or "Lark không cấp quyền đăng nhập.", 401)
        return
    if not code or not state:
        _error("Yêu cầu không hợp lệ", "Phản hồi đăng nhập thiếu code hoặc state.")
        return

    transaction = _consume_transaction(state)
    browser_binding = frappe.request.cookies.get(BINDING_COOKIE, "")
    frappe.local.cookie_manager.delete_cookie(BINDING_COOKIE)
    if not transaction or not browser_binding or not hmac.compare_digest(
        transaction.get("binding_hash", ""), sha256_hex(browser_binding)
    ):
        _error("Phiên đăng nhập đã hết hạn", "Hãy mở lại ứng dụng ERP trong Lark và thử lại.", 401)
        return

    try:
        config = load_configuration(os.environ)
        userinfo = _exchange_code(code, transaction, config)
        email = userinfo.get("email")
        if not isinstance(email, str) or not email.strip():
            raise ValueError("OIDC UserInfo did not include an email address")
    except (KeyError, TypeError, ValueError, jwt.PyJWTError, requests.RequestException):
        frappe.log_error(title="Letron SSO callback failed", message=frappe.get_traceback())
        _error("Không thể đăng nhập", "Auth Server không xác thực được tài khoản Lark.", 401)
        return

    if config.role_sync.enabled:
        try:
            snapshot = snapshot_from_payload(
                userinfo,
                max_age_seconds=config.role_sync.snapshot_max_age_seconds,
            )
            user = reconcile_identity(snapshot, config.role_sync, source="login", allow_create=True)
            frappe.db.commit()
        except SsoAccessDenied:
            frappe.db.commit()
            _error("Tài khoản chưa được cấp quyền ERP", "Tài khoản Lark chưa thuộc nhóm truy cập ERP.", 403)
            return
        except SsoSnapshotStale:
            frappe.db.rollback()
            _error("Không thể xác nhận quyền ERP", "Thông tin quyền từ Lark đã quá hạn.", 503)
            return
        except SsoIdentityConflict:
            frappe.db.commit()
            _error("Xung đột tài khoản ERP", "Danh tính Lark đang trùng với một tài khoản ERP khác.", 409)
            return
        except (TypeError, ValueError, frappe.ValidationError):
            frappe.db.rollback()
            frappe.log_error(title="Letron SSO role synchronization failed", message=frappe.get_traceback())
            _error("Không thể đồng bộ quyền ERP", "Không thể xác nhận quyền hiện tại từ Lark.", 503)
            return
    else:
        user = _authorized_erp_user(email)
        if not user:
            _error(
                "Tài khoản chưa được cấp quyền ERP",
                "Email Lark này chưa gắn với một System User đang hoạt động trong ERPNext.",
                403,
            )
            return

    frappe.local.login_manager.login_as(user)
    frappe.db.commit()
    _redirect("/desk")


def _snapshot_is_fresh(identity: Any, interval_seconds: int) -> bool:
    if not identity.last_sync_at:
        return False
    last_sync_at = frappe.utils.get_datetime(identity.last_sync_at)
    if last_sync_at is None:
        return False
    age = (frappe.utils.now_datetime() - last_sync_at).total_seconds()
    return -60 <= age <= interval_seconds


def _fetch_linked_identity_snapshot(identity: Any, config: Any) -> Any:
    if not config.role_sync.sync_url or not config.role_sync.sync_secret:
        raise ValueError("Lark role synchronization endpoint is not configured")
    response = requests.post(
        config.role_sync.sync_url,
        json={
            "tenant_key": identity.tenant_key,
            "subject": identity.subject,
            "subject_type": identity.subject_type,
        },
        headers={"Authorization": f"Bearer {config.role_sync.sync_secret}"},
        timeout=SYNC_HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("version") != 2:
        raise TypeError("Unsupported role snapshot version")
    item = payload.get("snapshot")
    if not isinstance(item, dict):
        raise TypeError("Role snapshot response is invalid")
    if item.get("status") not in {"ok", "disabled"}:
        raise SsoIdentityError(str(item.get("error_code") or item.get("status") or "snapshot_error"))
    snapshot = snapshot_from_payload(
        item,
        max_age_seconds=config.role_sync.snapshot_max_age_seconds,
    )
    if snapshot.identity_key != identity.name:
        raise SsoIdentityError("Role snapshot identity did not match the ERP link")
    return snapshot


def _deny_current_request(message: str) -> None:
    frappe.flags.disable_traceback = True
    raise frappe.AuthenticationError(message)


def _record_request_failure(identity_name: str, error_code: str, config: Any) -> None:
    frappe.db.rollback()
    record_sync_error(identity_name, error_code, config.role_sync, source="request")
    sync_state = frappe.db.get_value("Letron SSO Identity", identity_name, "sync_state")
    frappe.db.commit()
    if sync_state == "Stale Locked":
        _deny_current_request("Lark authorization could not be refreshed")


def enforce_lark_entitlement() -> None:
    """Refresh a linked user's Lark authorization lazily during authenticated requests."""

    user_name = frappe.session.user
    if user_name in {"", "Guest"} or not frappe.db.table_exists("Letron SSO Identity"):
        return
    if frappe.request.path in {"/api/method/logout", "/api/method/frappe.auth.logout"}:
        return

    identity_name = frappe.db.get_value("Letron SSO Identity", {"user": user_name}, "name")
    if not identity_name:
        return
    try:
        config = load_configuration(os.environ)
    except ValueError:
        _deny_current_request("Lark authorization is not configured")
        return
    if not config.role_sync.enabled:
        return

    identity = cast(Any, frappe.get_doc("Letron SSO Identity", identity_name))
    if identity.sync_state != "Active":
        _deny_current_request("Lark authorization is not active")
    if _snapshot_is_fresh(identity, config.role_sync.request_check_interval_seconds):
        return

    lock_key = f"letron:sso:request-sync:{identity_name}"
    cache = cast(Any, frappe.cache)
    with cache.lock(lock_key, timeout=SYNC_HTTP_TIMEOUT_SECONDS + 5, blocking_timeout=SYNC_HTTP_TIMEOUT_SECONDS + 5):
        identity = cast(Any, frappe.get_doc("Letron SSO Identity", identity_name))
        if identity.sync_state != "Active":
            _deny_current_request("Lark authorization is not active")
        if _snapshot_is_fresh(identity, config.role_sync.request_check_interval_seconds):
            return

        try:
            snapshot = _fetch_linked_identity_snapshot(identity, config)
        except (requests.RequestException, TypeError, ValueError) as error:
            _record_request_failure(identity_name, type(error).__name__, config)
            return

        previous_user = str(identity.user)
        try:
            reconciled_user = reconcile_identity(snapshot, config.role_sync, source="request", allow_create=False)
        except (SsoAccessDenied, SsoIdentityConflict):
            frappe.db.commit()
            _deny_current_request("Lark authorization was revoked")
            return
        except frappe.ValidationError as error:
            _record_request_failure(identity_name, type(error).__name__, config)
            return

        if reconciled_user != previous_user:
            from frappe.sessions import clear_sessions

            clear_sessions(user=previous_user, keep_current=False, force=True)
            clear_sessions(user=reconciled_user, keep_current=False, force=True)
            frappe.db.commit()
            _deny_current_request("Lark identity changed; sign in again")
            return
        frappe.db.commit()
