import argparse
import copy
import json
import re
from pathlib import Path

import yaml

from .contract import load_contract, validate_contract
from .metadata import discover_doctypes, discover_whitelisted_methods
from .models import serialize
from .openapi import build_openapi

ROOT = Path(__file__).resolve().parents[2]


def source_roots(root: Path):
    candidates = [("frappe", root / ".cache/frappe-v16/frappe"), ("erpnext", root / "apps/erpnext/erpnext"), ("letron_api", root / "apps/letron_api/letron_api")]
    return [(name, path) for name, path in candidates if path.exists()]


def collect(root: Path):
    roots = source_roots(root)
    return discover_doctypes(roots), discover_whitelisted_methods(roots)


def expand_typed_modules(contract, doctypes):
    modules = set(contract["runtime"].get("typed_modules", []))
    if not modules:
        return contract
    allowed = {item.module or "Uncategorized" for item in doctypes} if "*" in modules else modules
    by_name = {item.name: item for item in doctypes}
    selected = {
        item.name for item in doctypes if not item.is_child_table and (item.module or "Uncategorized") in allowed
    }
    pending = list(selected)
    while pending:
        current = by_name[pending.pop()]
        for field in current.fields:
            if field.fieldtype == "Table" and field.options in by_name and field.options not in selected:
                selected.add(field.options)
                pending.append(field.options)
    contract["runtime"]["typed_doctypes"] = sorted(selected)
    return contract


def generate(root: Path, output: Path) -> None:
    doctypes, methods = collect(root)
    contract = expand_typed_modules(load_contract(root / "contracts/erpnext-integration.yml"), doctypes)
    validate_contract(contract, doctypes, methods)
    config_path = root / "config.yml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        port = config.get("project", {}).get("http_port")
        if port and contract["runtime"]["server_url"].startswith("${"):
            contract["runtime"]["server_url"] = f"http://127.0.0.1:{port}"
    if contract["runtime"]["server_url"].startswith("${"):
        raise ValueError("runtime.server_url must resolve from ERPNEXT_API_URL or config.yml before generation")
    output.mkdir(parents=True, exist_ok=True)
    module_index: dict[str, list[str]] = {}
    for item in doctypes:
        module_index.setdefault(item.module or "Uncategorized", []).append(item.name)
    (output / "catalog.json").write_text(json.dumps({"doctypes": serialize(doctypes), "whitelisted_methods": serialize(methods), "modules": {key: sorted(value) for key, value in sorted(module_index.items())}}, indent=2, ensure_ascii=False), encoding="utf-8")
    spec = build_openapi(contract, doctypes, methods)
    (output / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "openapi.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    module_dir = output / "openapi" / "modules"
    module_dir.mkdir(parents=True, exist_ok=True)
    for stale in (*module_dir.glob("*.json"), *module_dir.glob("*.yaml")):
        stale.unlink()
    configured_public_modules = set(contract["runtime"].get("public_modules", []))
    all_modules = {item.module or "Uncategorized" for item in doctypes}
    module_names = sorted(all_modules & configured_public_modules) if configured_public_modules else sorted(all_modules)
    try:
        artifact_prefix = output.relative_to(root).as_posix()
    except ValueError:
        artifact_prefix = output.name
    by_name = {item.name: item for item in doctypes}
    typed_names = set(contract["runtime"].get("typed_doctypes", []))
    module_files: dict[str, dict[str, str]] = {}
    for module_name in module_names:
        selected = {item.name for item in doctypes if item.name in typed_names and (item.module or "Uncategorized") == module_name}
        pending = list(selected)
        while pending:
            current = by_name[pending.pop()]
            for field in current.fields:
                if field.fieldtype == "Table" and field.options in by_name and field.options not in selected:
                    selected.add(field.options)
                    pending.append(field.options)
        if not selected:
            continue
        module_contract = copy.deepcopy(contract)
        module_contract["runtime"]["typed_doctypes"] = sorted(selected)
        module_spec = build_openapi(module_contract, [by_name[name] for name in sorted(selected)], methods, module_name)
        slug = re.sub(r"[^a-z0-9]+", "-", module_name.lower()).strip("-") or "uncategorized"
        json_name = f"{slug}.json"
        yaml_name = f"{slug}.yaml"
        (module_dir / json_name).write_text(json.dumps(module_spec, indent=2, ensure_ascii=False), encoding="utf-8")
        (module_dir / yaml_name).write_text(yaml.safe_dump(module_spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
        module_files[module_name] = {"json": f"{artifact_prefix}/openapi/modules/{json_name}", "yaml": f"{artifact_prefix}/openapi/modules/{yaml_name}"}
    (output / "openapi" / "index.json").write_text(json.dumps({"modules": module_files}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"generated {len(doctypes)} doctypes and {len(methods)} methods")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect ERPNext source and generate integration artifacts")
    parser.add_argument("command", choices=["validate", "inspect", "generate", "handbook"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "validate":
        doctypes, methods = collect(root)
        contract = expand_typed_modules(load_contract(root / "contracts/erpnext-integration.yml"), doctypes)
        validate_contract(contract, doctypes, methods)
        print("contract valid")
    elif args.command == "inspect":
        doctypes, methods = collect(root)
        print(json.dumps({"doctype_count": len(doctypes), "method_count": len(methods), "sample_methods": [m.dotted_path for m in methods[:20]]}, indent=2))
    else:
        generate(root, (args.output or root / "contracts/generated").resolve())
        if args.command == "handbook":
            print("OpenAPI/catalog artifacts generated; handbook source is docs/ERPNext_Integration_Handbook.md")
    return 0
