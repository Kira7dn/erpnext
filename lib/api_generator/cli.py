import argparse
import copy
import json
import re
import tempfile
from pathlib import Path

import yaml

from .contract import load_contract, validate_contract
from .handoff import build_control_plane, write_handoff
from .metadata import discover_doctypes, discover_whitelisted_methods
from .models import serialize
from .openapi import build_openapi
from .registry import build_registry, registry_document
from .typescript import emit_types, emit_zod

ROOT = Path(__file__).resolve().parents[2]


def source_roots(root: Path):
    candidates = [("frappe", root / ".cache/frappe-v16/frappe"), ("erpnext", root / "apps/erpnext/erpnext"), ("letron_api", root / "apps/letron_api/letron_api")]
    return [(name, path) for name, path in candidates if path.exists()]


def collect(root: Path):
    roots = source_roots(root)
    return discover_doctypes(roots), discover_whitelisted_methods(roots)


def _local_schema(value):
    if isinstance(value, dict):
        return {key: (f"{value['$ref'].rsplit('/', 1)[-1]}.json" if key == "$ref" and isinstance(value.get("$ref"), str) and value["$ref"].startswith("#/components/schemas/") else _local_schema(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_local_schema(item) for item in value]
    return value


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


def generate(root: Path, output: Path, handoff: Path | None = None) -> None:
    doctypes, methods = collect(root)
    contract = expand_typed_modules(load_contract(root / "contracts/erpnext-integration.yml"), doctypes)
    validate_contract(contract, doctypes, methods)
    config_path = root / "config" / "config.yaml"
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        port = config.get("project", {}).get("http_port")
        if port and contract["runtime"]["server_url"].startswith("${"):
            contract["runtime"]["server_url"] = f"http://127.0.0.1:{port}"
    if contract["runtime"]["server_url"].startswith("${"):
        raise ValueError("runtime.server_url must resolve from ERPNEXT_API_URL or config/config.yaml before generation")
    output.mkdir(parents=True, exist_ok=True)
    module_index: dict[str, list[str]] = {}
    for item in doctypes:
        module_index.setdefault(item.module or "Uncategorized", []).append(item.name)
    (output / "catalog.json").write_text(json.dumps({"doctypes": serialize(doctypes), "whitelisted_methods": serialize(methods), "modules": {key: sorted(value) for key, value in sorted(module_index.items())}}, indent=2, ensure_ascii=False), encoding="utf-8")
    spec = build_openapi(contract, doctypes, methods)
    registry = build_registry(spec, contract)
    schemas = spec["components"]["schemas"]
    schema_dir = output / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    for stale in schema_dir.glob("*.json"):
        stale.unlink()
    for name, schema in schemas.items():
        schema_dir.joinpath(f"{name}.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"https://letron.local/schemas/{name}.json", **_local_schema(schema)}, indent=2, ensure_ascii=False), encoding="utf-8")
    operation_schema_dir = schema_dir / "operations"
    operation_schema_dir.mkdir(parents=True, exist_ok=True)
    for stale in operation_schema_dir.glob("*.json"):
        stale.unlink()
    for operation in registry:
        for suffix in ("request", "response"):
            schema = operation.get(f"{suffix}_schema")
            if schema:
                operation_schema_dir.joinpath(f"{operation['operation_id']}.{suffix}.json").write_text(json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"https://letron.local/schemas/operations/{operation['operation_id']}.{suffix}.json", **_local_schema(schema)}, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "types.ts").write_text(emit_types(schemas), encoding="utf-8")
    (output / "zod.ts").write_text(emit_zod(schemas, registry), encoding="utf-8")
    registry_meta = registry_document(registry)
    (output / "runtime-contract.json").write_text(json.dumps({"version": 1, "registry_version": registry_meta["version"], "registry_sha256": registry_meta["sha256"], "registry": registry, "schemas": schemas}, indent=2, ensure_ascii=False), encoding="utf-8")
    package_generated = root / "apps/letron_api/letron_api/generated"
    if output.resolve() == (root / "contracts/generated").resolve():
        package_generated.mkdir(parents=True, exist_ok=True)
        (package_generated / "runtime-contract.json").write_text(json.dumps({"version": 1, "registry_version": registry_meta["version"], "registry_sha256": registry_meta["sha256"], "registry": registry, "schemas": schemas}, indent=2, ensure_ascii=False), encoding="utf-8")
        frontend_generated = root / "apps/erp/src/generated"
        frontend_generated.mkdir(parents=True, exist_ok=True)
        (frontend_generated / "types.ts").write_text(emit_types(schemas), encoding="utf-8")
        (frontend_generated / "zod.ts").write_text(emit_zod(schemas, registry), encoding="utf-8")
    catalog = {"version": 1, "registry_version": registry_meta["version"], "registry_sha256": registry_meta["sha256"], "doctypes": serialize(doctypes), "whitelisted_methods": serialize(methods), "modules": {key: sorted(value) for key, value in sorted(module_index.items())}, "operations": registry}
    (output / "catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "registry.json").write_text(json.dumps(registry_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "openapi.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    module_dir = output / "openapi" / "modules"
    module_dir.mkdir(parents=True, exist_ok=True)
    for stale in (*module_dir.glob("*.json"), *module_dir.glob("*.yaml")):
        stale.unlink()
    public_resources = {item["doctype"] for item in contract["runtime"].get("public_resources", [])}
    module_names = sorted(
        {item.module or "Uncategorized" for item in doctypes if item.name in public_resources}
        | {item["module"] for item in contract["runtime"].get("custom_routes", [])}
    )
    try:
        artifact_prefix = output.relative_to(root).as_posix()
    except ValueError:
        artifact_prefix = output.name
    by_name = {item.name: item for item in doctypes}
    module_files: dict[str, dict[str, str]] = {}
    for module_name in module_names:
        selected = {item.name for item in doctypes if item.name in public_resources and (item.module or "Uncategorized") == module_name}
        pending = list(selected)
        while pending:
            current = by_name[pending.pop()]
            for field in current.fields:
                if field.fieldtype == "Table" and field.options in by_name and field.options not in selected:
                    selected.add(field.options)
                    pending.append(field.options)
        if not selected and not any(item["module"] == module_name for item in contract["runtime"].get("custom_routes", [])):
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
    if handoff is not None:
        write_handoff(handoff, spec, build_control_plane(contract["runtime"]["server_url"]))
    print(f"generated {len(doctypes)} doctypes and {len(methods)} methods")


def check_handoff(root: Path) -> None:
    expected = root / "contracts" / "openapi"
    if not expected.is_dir():
        raise ValueError("Missing committed contracts/openapi handoff artifacts")
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        generated = temporary / "generated"
        handoff = temporary / "openapi"
        generate(root, generated, handoff)
        expected_files = {path.name for path in expected.iterdir() if path.is_file()}
        actual_files = {path.name for path in handoff.iterdir() if path.is_file()}
        if expected_files != actual_files:
            raise ValueError("Committed OpenAPI handoff file set is stale")
        stale = [name for name in sorted(actual_files) if (expected / name).read_bytes() != (handoff / name).read_bytes()]
        if stale:
            raise ValueError("Committed OpenAPI handoff artifacts are stale: " + ", ".join(stale))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect ERPNext source and generate integration artifacts")
    parser.add_argument("command", choices=["validate", "inspect", "generate", "check", "handbook"])
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
    elif args.command == "check":
        check_handoff(root)
        print("committed OpenAPI handoff artifacts are current")
    else:
        generate(
            root,
            (args.output or root / "contracts/generated").resolve(),
            root / "contracts" / "openapi",
        )
        if args.command == "handbook":
            print("OpenAPI/catalog artifacts generated; handbook source is docs/Integration_Handbook.md")
    return 0
