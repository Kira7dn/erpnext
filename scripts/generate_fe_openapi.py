"""Generate the scoped FE OpenAPI from an explicit API inventory."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "contracts" / "apps-erp.api.json"
PUBLIC = ROOT / "contracts" / "openapi" / "public.json"
OUTPUT = ROOT / "contracts" / "apps-erp.api.yml"


def refs(value: Any) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/"):
            _, _, kind, name = ref.split("/", 3)
            found.add((kind, name.replace("~1", "/").replace("~0", "~")))
        for child in value.values():
            found.update(refs(child))
    elif isinstance(value, list):
        for child in value:
            found.update(refs(child))
    return found


def generate() -> dict[str, Any]:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    public = json.loads(PUBLIC.read_text(encoding="utf-8"))
    paths: dict[str, Any] = {}
    for method, path in inventory["operations"]:
        operation = public.get("paths", {}).get(path, {}).get(method.lower())
        if operation is None:
            raise ValueError(f"missing operation in public contract: {method} {path}")
        operation = copy.deepcopy(operation)
        operation["tags"] = [tag for tag in operation.get("tags", []) if tag.startswith("Module: ")]
        paths.setdefault(path, {})[method.lower()] = operation
    components: dict[str, Any] = {}
    pending = refs(paths)
    while pending:
        kind, name = pending.pop()
        if name in components.get(kind, {}):
            continue
        source = public.get("components", {}).get(kind, {})
        if name not in source:
            raise ValueError(f"missing component in public contract: {kind}/{name}")
        components.setdefault(kind, {})[name] = copy.deepcopy(source[name])
        pending.update(refs(source[name]))
    return {
        "openapi": public["openapi"],
        "info": {"title": "Letron ERP frontend API", "version": public["info"]["version"]},
        "servers": public.get("servers", []),
        "paths": paths,
        "components": components,
            "x-operation-inventory": "apps-erp.api.json",
            "x-contract-source": "openapi/public.json",
    }


def main() -> int:
    contract = generate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"generated {sum(len(item) for item in contract['paths'].values())} operations into {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
