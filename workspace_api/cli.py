import argparse
import json
from pathlib import Path

import yaml

from .contract import load_contract
from .metadata import discover_doctypes, discover_whitelisted_methods
from .models import serialize
from .openapi import build_openapi

ROOT = Path(__file__).resolve().parent.parent


def source_roots(root: Path):
    candidates = [("frappe", root / ".cache/frappe-v16/frappe"), ("erpnext", root / "erpnext/erpnext"), ("letron_api", root / "apps/letron_api/letron_api")]
    return [(name, path) for name, path in candidates if path.exists()]


def collect(root: Path):
    roots = source_roots(root)
    return discover_doctypes(roots), discover_whitelisted_methods(roots)


def generate(root: Path, output: Path) -> None:
    contract = load_contract(root / "contracts/erpnext-integration.yml")
    doctypes, methods = collect(root)
    output.mkdir(parents=True, exist_ok=True)
    (output / "catalog.json").write_text(json.dumps({"doctypes": serialize(doctypes), "whitelisted_methods": serialize(methods)}, indent=2, ensure_ascii=False), encoding="utf-8")
    spec = build_openapi(contract, doctypes, methods)
    (output / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "openapi.yaml").write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"generated {len(doctypes)} doctypes and {len(methods)} methods")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inspect ERPNext source and generate integration artifacts")
    parser.add_argument("command", choices=["validate", "inspect", "generate"])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "validate":
        load_contract(root / "contracts/erpnext-integration.yml")
        print("contract valid")
    elif args.command == "inspect":
        doctypes, methods = collect(root)
        print(json.dumps({"doctype_count": len(doctypes), "method_count": len(methods), "sample_methods": [m.dotted_path for m in methods[:20]]}, indent=2))
    else:
        generate(root, (args.output or root / "generated").resolve())
    return 0
