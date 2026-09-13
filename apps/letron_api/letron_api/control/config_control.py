"""Fixed-path administrative API for the two compute-local YAML sources."""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import frappe

from letron_api.control import policy, system_config

MAX_CONFIGURATION_BYTES = 2 * 1024 * 1024


def _source(kind: str) -> Path:
    sources = {
        "config": system_config.config_path(),
        "policy": system_config.policy_path(),
    }
    if kind not in sources:
        frappe.throw("kind must be config or policy", exc=frappe.ValidationError)
    return sources[kind]


def _source_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _require_manager() -> None:
    frappe.only_for("System Manager")


@contextmanager
def _configuration_lock(directory: Path) -> Iterator[None]:
    lock = directory / ".letron-config.lock"
    deadline = time.monotonic() + 10
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                frappe.throw("Configuration is being updated by another request", exc=frappe.ValidationError)
            time.sleep(0.05)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink(missing_ok=True)


def _validate_candidate(kind: str, candidate: Path) -> dict[str, Any]:
    if kind == "config":
        validation = system_config.validate_file(candidate)
        system_config.validate_bundle(candidate, system_config.policy_path())
        return validation
    validation = policy.validate_file(candidate)
    system_config.validate_bundle(system_config.config_path(), candidate)
    return validation


def _conflict(message: str) -> None:
    frappe.throw(message, exc=frappe.DuplicateEntryError)


def _atomic_replace(source: Path, content: str, mode: int) -> None:
    temporary = source.with_name(f".{source.name}.{os.getpid()}.replace")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, source)
    finally:
        temporary.unlink(missing_ok=True)


def _assert_bootstrap_immutable(candidate: Path) -> None:
    current_company = policy.load_policy()["bootstrap"]["company"]
    candidate_company = policy.load_policy(candidate)["bootstrap"]["company"]
    if current_company != candidate_company:
        _conflict(
            "bootstrap.company is immutable after tenant initialization; use an explicit Company migration"
        )


@frappe.whitelist(methods=["GET"])
def get_configuration(kind: str | None = None) -> dict[str, Any]:
    """Read one validated YAML SOT without resolving or returning secrets."""

    _require_manager()
    if not kind and frappe.request:
        kind = frappe.request.args.get("kind")
    if not kind:
        frappe.throw("kind is required", exc=frappe.ValidationError)
    if not isinstance(kind, str):
        frappe.throw("kind must be a string", exc=frappe.ValidationError)
    kind = cast(str, kind)
    source = _source(kind)
    content = source.read_text(encoding="utf-8")
    validation = _validate_candidate(kind, source)
    return {
        "kind": kind,
        "content": content,
        "source_sha256": _source_sha256(content),
        "state_sha256": validation["sha256"],
        "schema_version": validation["schema_version"],
        "scope_version": validation.get("scope_version", policy.POLICY_SCOPE_VERSION if kind == "policy" else None),
        "completeness": validation.get("completeness", {}),
    }


@frappe.whitelist(methods=["PUT", "POST"])
def put_configuration(
    kind: str,
    content: str,
    expected_source_sha256: str,
    apply_now: int | str | bool = True,
) -> dict[str, Any]:
    """Validate, atomically replace and optionally reconcile one fixed YAML file."""

    _require_manager()
    if not isinstance(content, str):
        frappe.throw("content must be UTF-8 YAML text", exc=frappe.ValidationError)
    if len(content.encode("utf-8")) > MAX_CONFIGURATION_BYTES:
        frappe.throw("Configuration exceeds the 2 MiB limit", exc=frappe.ValidationError)
    source = _source(kind)
    with _configuration_lock(source.parent):
        current = source.read_text(encoding="utf-8")
        if expected_source_sha256 != _source_sha256(current):
            _conflict("Configuration changed; reload before saving")
        candidate = source.with_name(f".{source.name}.{os.getpid()}.candidate")
        candidate_config: dict[str, Any] | None = None
        try:
            candidate.write_text(content, encoding="utf-8", newline="\n")
            validation = _validate_candidate(kind, candidate)
            if kind == "policy":
                _assert_bootstrap_immutable(candidate)
            else:
                candidate_config = system_config.load_config(candidate)
        finally:
            candidate.unlink(missing_ok=True)

        should_apply = str(apply_now).lower() not in {"0", "false", "no"}
        runtime_config = candidate_config if candidate_config is not None else system_config.load_config()
        if not should_apply and runtime_config["credentials"]["production_like"]:
            frappe.throw("apply_now=false is restricted to developer test sites", exc=frappe.ValidationError)

        previous_mode = source.stat().st_mode & 0o777
        _atomic_replace(source, content, previous_mode)
        try:
            if should_apply:
                if kind == "config":
                    reconciliation = system_config.apply()
                else:
                    policy.reset_policy_cache()
                    reconciliation = policy.apply()
            else:
                reconciliation = {"applied": 0, "restart_required": kind == "config"}
        except Exception as apply_error:  # noqa: BLE001 - compensate any native apply failure
            _atomic_replace(source, current, previous_mode)
            try:
                if kind == "config":
                    system_config.apply()
                else:
                    policy.reset_policy_cache()
                    policy.apply()
            except Exception as rollback_error:
                frappe.log_error(
                    title="Letron configuration rollback failed",
                    message=f"apply={apply_error!r}\nrollback={rollback_error!r}",
                )
                raise RuntimeError(
                    "Configuration apply and rollback both failed; runtime health is not trustworthy"
                ) from rollback_error
            frappe.throw(
                f"Configuration apply failed; YAML and runtime were restored: {type(apply_error).__name__}",
                exc=frappe.ValidationError,
            )

    updated = source.read_text(encoding="utf-8")
    return {
        "ok": True,
        "kind": kind,
        "source_sha256": _source_sha256(updated),
        "state_sha256": validation["sha256"],
        "schema_version": validation["schema_version"],
        "scope_version": validation.get("scope_version", policy.POLICY_SCOPE_VERSION if kind == "policy" else None),
        "completeness": validation.get("completeness", {}),
        "applied": reconciliation.get("applied", 0),
        "drift_count": reconciliation.get("drift_count"),
        "restart_required": bool(reconciliation.get("restart_required", False)),
    }
