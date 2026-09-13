"""Runtime validation against the generated public business contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, RefResolver

_CONTRACT: dict[str, Any] | None = None
_CONTRACT_MTIME_NS: int | None = None


def _load_contract() -> dict[str, Any]:
    global _CONTRACT, _CONTRACT_MTIME_NS
    path = Path(__file__).with_name("generated") / "runtime-contract.json"
    if not path.exists():
        path = Path(__file__).resolve().parents[3] / "contracts/generated/runtime-contract.json"
    mtime_ns = path.stat().st_mtime_ns
    if _CONTRACT is not None and _CONTRACT_MTIME_NS == mtime_ns:
        return _CONTRACT
    _CONTRACT = json.loads(path.read_text(encoding="utf-8"))
    _CONTRACT_MTIME_NS = mtime_ns
    return _CONTRACT


def public_route_maps() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], set[str]], dict[tuple[str, str, str], str]]:
    """Return route/action maps generated from the public contract registry."""

    resources: dict[tuple[str, str], str] = {}
    document_actions: dict[tuple[str, str], set[str]] = {}
    custom_actions: dict[tuple[str, str, str], str] = {}
    for entry in _load_contract()["registry"]:
        module = entry.get("module")
        resource = entry.get("resource")
        target = entry.get("target") or {}
        doctype = target.get("doctype")
        action = target.get("action")
        if not isinstance(module, str) or not isinstance(resource, str):
            continue
        if isinstance(doctype, str) and isinstance(action, str):
            handler = target.get("handler")
            if action in {"submit", "cancel"}:
                document_actions.setdefault((module, resource), set()).add(action)
            elif isinstance(handler, str):
                custom_actions[(module, resource, action)] = handler
        elif isinstance(doctype, str):
            resources[(module, resource)] = doctype
    return resources, document_actions, custom_actions


def contract_metadata() -> tuple[int, str]:
    contract = _load_contract()
    version = contract.get("registry_version", contract.get("version"))
    sha256 = contract.get("registry_sha256")
    if not isinstance(version, int) or not isinstance(sha256, str) or len(sha256) != 64:
        raise ValueError("Generated registry metadata is missing or invalid")
    return version, sha256


def _entry(method: str, path: str) -> dict[str, Any] | None:
    parts = path.strip("/").split("/")
    for item in _load_contract()["registry"]:
        pattern = item["path"].strip("/").split("/")
        if item["method"] != method.upper() or len(pattern) != len(parts):
            continue
        if all(expected.startswith("{") or expected == actual for expected, actual in zip(pattern, parts, strict=True)):
            return item
    return None


def _validate(schema: dict[str, Any], value: Any) -> None:
    root = {"components": {"schemas": _load_contract()["schemas"]}}
    resolver = RefResolver.from_schema(root)
    errors = sorted(Draft202012Validator(schema, resolver=resolver).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        detail = [{"path": list(error.path), "message": error.message} for error in errors[:20]]
        raise ValueError(json.dumps({"error": "schema_validation_failed", "field_errors": detail}, ensure_ascii=False))


def validate_request(method: str, path: str, body: bytes) -> None:
    entry = _entry(method, path)
    if not entry or not entry.get("request_schema"):
        return
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON request body") from exc
    _validate(entry["request_schema"], value)


def validate_response(method: str, path: str, value: Any) -> None:
    entry = _entry(method, path)
    if entry and entry.get("response_schema"):
        _validate(entry["response_schema"], value)
