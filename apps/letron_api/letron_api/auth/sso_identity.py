from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import frappe

IDENTITY_DOCTYPE = "Letron SSO Identity"
AUDIT_DOCTYPE = "Letron SSO Audit Log"


class SsoIdentityError(ValueError):
    pass


class SsoIdentityConflict(SsoIdentityError):
    pass


@dataclass(frozen=True)
class IdentitySnapshot:
    tenant_key: str
    subject: str
    subject_type: str
    email: str
    display_name: str
    provisioned_at: datetime

    @property
    def identity_key(self) -> str:
        return hashlib.sha256(f"lark\0{self.tenant_key}\0{self.subject}".encode()).hexdigest()


def _frappe_datetime(value: datetime) -> datetime:
    return frappe.utils.convert_utc_to_system_timezone(value).replace(tzinfo=None)


def _audit(
    event_type: str,
    *,
    source: str,
    outcome: str,
    identity: str | None = None,
    user: str | None = None,
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
            "detail": json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
        }
    )
    document.insert(ignore_permissions=True)


def _identity(name: str) -> Any | None:
    return cast(Any, frappe.get_doc(IDENTITY_DOCTYPE, name)) if frappe.db.exists(IDENTITY_DOCTYPE, name) else None


def _create_user(snapshot: IdentitySnapshot) -> Any:
    if frappe.db.exists("User", snapshot.email):
        raise SsoIdentityConflict("Email already belongs to an unlinked ERP user")
    # This is an identity anchor only. Auth Portal owns authorization.
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": snapshot.email,
            "first_name": snapshot.display_name,
            "enabled": 1,
            "user_type": "Website User",
            "send_welcome_email": 0,
            "new_password": frappe.generate_hash(length=32),
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
        user = cast(Any, frappe.get_doc("User", snapshot.email))
        identity.reload()
    if user.first_name != snapshot.display_name:
        user.flags.lark_sso_sync = True
        user.first_name = snapshot.display_name
        user.save(ignore_permissions=True)
    return user


def _provision_identity_snapshot(snapshot: IdentitySnapshot) -> dict[str, Any]:
    identity = _identity(snapshot.identity_key)
    created = identity is None
    if identity is None:
        if frappe.db.exists("User", snapshot.email):
            linked = frappe.db.exists(IDENTITY_DOCTYPE, {"user": snapshot.email})
            if linked:
                raise SsoIdentityConflict("Email already belongs to another stable Lark identity")
            user = cast(Any, frappe.get_doc("User", snapshot.email))
            user.flags.lark_sso_sync = True
            user.enabled = 1
            user.user_type = "Website User"
            user.save(ignore_permissions=True)
        else:
            user = _create_user(snapshot)
        identity = frappe.get_doc(
            {
                "doctype": IDENTITY_DOCTYPE,
                "name": snapshot.identity_key,
                "identity_key": snapshot.identity_key,
                "provider": "lark",
                "tenant_key": snapshot.tenant_key,
                "subject": snapshot.subject,
                "subject_type": snapshot.subject_type,
                "user": user.name,
                "email": snapshot.email,
                "display_name": snapshot.display_name,
                "provisioned_at": _frappe_datetime(snapshot.provisioned_at),
            }
        )
        identity.insert(ignore_permissions=True)
    else:
        user = cast(Any, frappe.get_doc("User", identity.user))
        user = _update_profile(identity, user, snapshot)
        if not int(user.enabled):
            user.flags.lark_sso_sync = True
            user.enabled = 1
            user.user_type = "Website User"
            user.save(ignore_permissions=True)
        for field, value in {
            "email": snapshot.email,
            "display_name": snapshot.display_name,
            "provisioned_at": _frappe_datetime(snapshot.provisioned_at),
        }.items():
            frappe.db.set_value(IDENTITY_DOCTYPE, identity.name, field, value, update_modified=True)
    context = getattr(frappe.local, "letron_request_identity", {})
    audit_context = {
        key: context[key]
        for key in ("auth_source", "request_id", "policy_version", "erp_principal")
        if isinstance(context, dict) and context.get(key) is not None
    }
    _audit(
        "identity.jit_provisioned" if created else "identity.jit_refreshed",
        source="request",
        outcome="success",
        identity=identity.name,
        user=user.name,
        detail={"actor": "auth_portal", "roles_changed": False, **audit_context},
    )
    frappe.db.commit()
    return {"ok": True, "user": user.name, "identity": identity.name, "created": created}


@frappe.whitelist(allow_guest=True)
def provision_identity() -> dict[str, Any]:
    """JIT-provision only the ERP identity anchor after Auth authorization."""

    if not getattr(frappe.local, "letron_jit_authorized", False):
        frappe.throw("ERP identity provisioning authorization required", exc=frappe.AuthenticationError)
    payload = frappe.local.request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        frappe.throw("Invalid identity payload", exc=frappe.ValidationError)
    tenant_key = str(payload.get("tenant_key", "")).strip()
    subject = str(payload.get("subject", "")).strip()
    subject_type = str(payload.get("subject_type", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    display_name = str(payload.get("display_name", "")).strip() or email
    if not tenant_key or not subject or subject_type != "union_id" or not email or "@" not in email:
        frappe.throw("Invalid stable Lark identity", exc=frappe.ValidationError)
    snapshot = IdentitySnapshot(
        tenant_key=tenant_key,
        subject=subject,
        subject_type=subject_type,
        email=email,
        display_name=display_name,
        provisioned_at=datetime.now(UTC),
    )
    cache = cast(Any, frappe.cache)()
    with cache.lock(f"letron:identity:provision:{snapshot.identity_key}", timeout=15, blocking_timeout=15):
        return _provision_identity_snapshot(snapshot)


def status() -> dict[str, Any]:
    if not frappe.db.table_exists(IDENTITY_DOCTYPE):
        return {"enabled": True, "installed": False}
    identity_rows = frappe.get_all(IDENTITY_DOCTYPE, fields=["user"])
    active_count = sum(bool(frappe.db.get_value("User", row.user, "enabled")) for row in identity_rows)
    latest_rows = frappe.get_all(
        IDENTITY_DOCTYPE,
        fields=["provisioned_at"],
        filters={"provisioned_at": ["is", "set"]},
        order_by="provisioned_at desc",
        limit=1,
    )
    latest = latest_rows[0].provisioned_at if latest_rows else None
    return {
        "enabled": True,
        "installed": True,
        "identities": len(identity_rows),
        "states": {"Active": active_count, "Disabled": len(identity_rows) - active_count},
        "last_successful_sync_at": str(latest) if latest else None,
    }
