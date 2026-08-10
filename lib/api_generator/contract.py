import re
from pathlib import Path
from typing import Any

import yaml

REQUIRED = ("version", "kind", "runtime", "transport", "headers", "documentation")


def _list_of_strings(value: Any, name: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise TypeError(f"{name} must be a list of non-empty strings")


def validate_contract(data: dict[str, Any], doctypes: list[Any] | None = None, methods: list[Any] | None = None) -> dict[str, Any]:
    runtime = data["runtime"]
    for key in ("typed_doctypes", "include_methods"):
        _list_of_strings(runtime.get(key, []), f"runtime.{key}")
    _list_of_strings(runtime.get("typed_modules", []), "runtime.typed_modules")
    _list_of_strings(runtime.get("public_modules", []), "runtime.public_modules")
    unknown_public_modules = sorted(set(runtime.get("public_modules", [])) - set(runtime.get("typed_modules", [])))
    if unknown_public_modules:
        raise ValueError(f"runtime.public_modules must be included in typed_modules: {', '.join(unknown_public_modules)}")
    if runtime.get("group_by", "module") != "module":
        raise ValueError("runtime.group_by must be module")
    public_resources = runtime.get("public_resources", [])
    if not isinstance(public_resources, list) or any(not isinstance(item, dict) for item in public_resources):
        raise TypeError("runtime.public_resources must be a list of mappings")
    seen_paths: set[str] = set()
    for item in public_resources:
        if not isinstance(item.get("doctype"), str) or not item["doctype"] or not isinstance(item.get("path"), str) or not item["path"].startswith("/"):
            raise ValueError("runtime.public_resources entries require doctype and absolute path")
        if item["path"] in seen_paths:
            raise ValueError(f"runtime.public_resources path collision: {item['path']}")
        seen_paths.add(item["path"])
    actions = runtime.get("document_actions", [])
    if not isinstance(actions, list) or any(not isinstance(item, dict) for item in actions):
        raise TypeError("runtime.document_actions must be a list of mappings")
    for item in actions:
        if not isinstance(item.get("doctype"), str) or not item["doctype"] or not isinstance(item.get("module"), str) or not item["module"]:
            raise ValueError("runtime.document_actions entries require doctype and module")
        if not isinstance(item.get("actions"), list) or any(action not in {"submit", "cancel"} for action in item["actions"]):
            raise ValueError("runtime.document_actions actions must contain submit or cancel")
        if item["module"] not in runtime.get("public_modules", []):
            raise ValueError(f"runtime.document_actions module must be public: {item['module']}")
    for key in ("include_generic_resource_api", "include_generic_rpc_fallback", "include_doctype_metadata"):
        if not isinstance(runtime.get(key), bool):
            raise TypeError(f"runtime.{key} must be boolean")
    if not isinstance(runtime.get("server_url"), str) or not runtime["server_url"].strip():
        raise ValueError("runtime.server_url must be a non-empty string")
    auth = data.get("auth")
    if not isinstance(auth, dict) or not isinstance(auth.get("scheme"), str) or not auth["scheme"]:
        raise ValueError("auth.scheme must be a non-empty string")
    if doctypes is not None:
        available = {item.name for item in doctypes}
        unknown = sorted(set(runtime["typed_doctypes"]) - available)
        if unknown:
            raise ValueError(f"runtime.typed_doctypes contains unknown DocType: {', '.join(unknown)}")
        aliases = {item["doctype"] for item in runtime["public_resources"]}
        unknown_aliases = sorted(aliases - available)
        if unknown_aliases:
            raise ValueError(f"runtime.public_resources contains unknown DocType: {', '.join(unknown_aliases)}")
        unknown_actions = sorted({item["doctype"] for item in runtime.get("document_actions", [])} - available)
        if unknown_actions:
            raise ValueError(f"runtime.document_actions contains unknown DocType: {', '.join(unknown_actions)}")
        names: dict[str, str] = {}
        for item in doctypes:
            if item.name not in runtime["typed_doctypes"]:
                continue
            normalized = re.sub(r"[^A-Za-z0-9_]", "", item.name) or "FrappeDocument"
            if normalized in names and names[normalized] != item.name:
                raise ValueError(f"schema name collision: {names[normalized]} and {item.name}")
            names[normalized] = item.name
    if methods is not None:
        available = {item.dotted_path for item in methods}
        unknown = sorted(set(runtime["include_methods"]) - available)
        if unknown:
            raise ValueError(f"runtime.include_methods contains unknown method: {', '.join(unknown)}")
    return data


def load_contract(path: Path, doctypes: list[Any] | None = None, methods: list[Any] | None = None) -> dict[str, Any]:
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
    for section in ("runtime", "transport", "headers", "documentation"):
        if not isinstance(data[section], dict):
            raise TypeError(f"{section} must be a mapping")
    for key in ("rest", "webhook", "realtime"):
        if not isinstance(data["transport"].get(key), bool):
            raise TypeError(f"transport.{key} must be boolean")
    for key in ("request_id", "idempotency_key"):
        if not isinstance(data["headers"].get(key), str) or not data["headers"][key]:
            raise ValueError(f"headers.{key} must be a non-empty string")
    return validate_contract(data, doctypes, methods)
