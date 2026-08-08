from pathlib import Path
from typing import Any

import yaml

REQUIRED = ("version", "kind", "runtime", "transport", "headers", "documentation")


def load_contract(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("contract root must be a mapping")
    missing = [key for key in REQUIRED if key not in data]
    if missing:
        raise ValueError(f"contract missing required keys: {', '.join(missing)}")
    if data["kind"] != "erpnext-integration-contract":
        raise ValueError("contract kind must be erpnext-integration-contract")
    runtime = data["runtime"]
    if not isinstance(runtime, dict) or runtime.get("openapi_version") != "3.1.0":
        raise ValueError("runtime.openapi_version must be 3.1.0")
    for section in ("runtime", "transport"):
        if not isinstance(data[section], dict):
            raise TypeError(f"{section} must be a mapping")
    for key in ("rest", "webhook", "realtime"):
        if not isinstance(data["transport"].get(key), bool):
            raise TypeError(f"transport.{key} must be boolean")
    for key in ("request_id", "idempotency_key"):
        if not isinstance(data["headers"].get(key), str) or not data["headers"][key]:
            raise ValueError(f"headers.{key} must be a non-empty string")
    return data
