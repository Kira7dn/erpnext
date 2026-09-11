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
