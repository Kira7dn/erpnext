"""Generate an exhaustive, machine-readable ERPNext/Frappe DocType inventory.

This is deliberately broader than the policy wrapper.  Every native DocType
schema is retained verbatim so that classification can fail closed instead of
silently losing a field, default, false value, child table, permission, or
future upstream addition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

APP_NAMES = ("frappe", "erpnext")
CONFIG_NAME_PARTS = (
    "authorization",
    "category",
    "default",
    "permission",
    "policy",
    "profile",
    "rule",
    "setting",
    "template",
    "workflow",
)


def _schema_fingerprint(schema: dict[str, Any], child_schemas: dict[str, dict[str, Any]]) -> str:
    fields = []
    for field in schema.get("fields") or []:
        fields.append({key: field.get(key) for key in ("fieldname", "fieldtype", "options", "reqd", "default")})
    child = {}
    for field in schema.get("fields") or []:
        if field.get("fieldtype") == "Table" and field.get("options") in child_schemas:
            child[field["options"]] = child_schemas[field["options"]].get("fields") or []
    payload = json.dumps({"name": schema.get("name"), "fields": fields, "children": child}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _version(app_root: Path, app_name: str) -> str | None:
    init_path = app_root / app_name / "__init__.py"
    if not init_path.exists():
        return None
    match = re.search(
        r"^__version__\s*=\s*['\"]([^'\"]+)['\"]",
        init_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else None


def _candidate_reasons(schema: dict[str, Any]) -> list[str]:
    name = str(schema.get("name", "")).casefold()
    reasons: list[str] = []
    if schema.get("issingle"):
        reasons.append("single-doctype")
    if schema.get("document_type") == "Setup":
        reasons.append("document-type-setup")
    for part in CONFIG_NAME_PARTS:
        if part in name:
            reasons.append(f"name-contains-{part}")
    return reasons


def build_inventory(apps_root: Path, scope_path: Path | None = None) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    if scope_path is not None:
        scope = json.loads(scope_path.read_text(encoding="utf-8")) if scope_path.suffix == ".json" else __import__("yaml").safe_load(scope_path.read_text(encoding="utf-8"))
    scope_sources = {
        str(item["name"]): item
        for item in scope.get("sources", [])
        if isinstance(item, dict) and item.get("name")
    }
    public_modules = set(scope.get("public_modules", []))
    public_resources = set(scope.get("public_resources", []))
    policy_classifications = {"managed", "conditional"}
    doctypes: list[dict[str, Any]] = []
    app_versions: dict[str, str | None] = {}
    field_count = 0

    for app_name in APP_NAMES:
        app_root = apps_root / app_name
        if not app_root.exists() and app_name == "erpnext":
            workspace_erpnext = Path(__file__).resolve().parents[3] / "apps" / "erpnext"
            if workspace_erpnext.exists():
                app_root = workspace_erpnext
        if not app_root.exists() and app_name == "frappe" and (apps_root / "frappe").exists():
            app_root = apps_root / "frappe"
        if not app_root.exists():
            raise FileNotFoundError(f"Installed app source not found: {app_root}")
        app_versions[app_name] = _version(app_root, app_name)
        pattern_root = app_root / app_name
        raw_schemas: dict[str, dict[str, Any]] = {}
        for source in sorted(pattern_root.glob("**/doctype/*/*.json")):
            try:
                candidate = json.loads(source.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and candidate.get("doctype") == "DocType" and candidate.get("name"):
                raw_schemas[str(candidate["name"])] = candidate
        for source in sorted(pattern_root.glob("**/doctype/*/*.json")):
            schema = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(schema, dict):
                continue
            if schema.get("doctype") != "DocType" or not schema.get("name"):
                continue
            reasons = _candidate_reasons(schema)
            classification = "child-table" if schema.get("istable") else "unclassified"
            if not schema.get("istable") and str(schema["name"]) in scope_sources:
                classification = str(scope_sources[str(schema["name"])].get("classification", "unknown"))
            elif not schema.get("istable"):
                module = str(schema.get("module", ""))
                if str(schema["name"]) in public_resources:
                    classification = "entity"
                elif module in public_modules and reasons:
                    classification = "conditional"
                else:
                    classification = "excluded"
            if reasons and classification == "unclassified":
                classification = "policy-candidate"
            fields = schema.get("fields") or []
            field_count += len(fields)
            doctypes.append(
                {
                    "app": app_name,
                    "source": source.relative_to(app_root).as_posix(),
                    "classification": classification,
                    "candidate_reasons": reasons,
                    "schema_fingerprint": _schema_fingerprint(schema, raw_schemas),
                    "schema": schema,
                }
            )

    doctypes.sort(key=lambda item: (item["app"], item["schema"]["name"]))
    inventory_by_name = {str(item["schema"]["name"]): item for item in doctypes}
    missing_scope_sources = sorted(set(scope_sources) - set(inventory_by_name))
    schema_drift = []
    missing_fingerprints = []
    missing_acceptance = []
    for name, source in scope_sources.items():
        fingerprint = source.get("schema_fingerprint")
        if not isinstance(fingerprint, dict) or not fingerprint.get("sha256"):
            missing_fingerprints.append(name)
        elif name in inventory_by_name and fingerprint["sha256"] != inventory_by_name[name]["schema_fingerprint"]:
            schema_drift.append(name)
        if source.get("classification") in policy_classifications:
            acceptance = source.get("acceptance")
            required_acceptance = {
                "fixture_builder",
                "structural_test",
                "cleanup_handler",
                "dependency_prerequisites",
                "controller_effect_assertion",
            }
            if not isinstance(acceptance, dict) or required_acceptance - set(acceptance):
                missing_acceptance.append(name)
    summary = {
        "doctypes": len(doctypes),
        "fields": field_count,
        "policy_candidates": sum(
            item["classification"] == "policy-candidate" for item in doctypes
        ),
        "child_tables": sum(item["classification"] == "child-table" for item in doctypes),
        "unclassified": sum(item["classification"] in {"unclassified", "unknown"} for item in doctypes),
        "unknown": sum(item["classification"] in {"unclassified", "unknown"} for item in doctypes),
        "scope_sources_missing_from_native": len(missing_scope_sources),
        "scope_entries_missing_fingerprint": len(missing_fingerprints),
        "managed_entries_without_acceptance": len(missing_acceptance),
        "schema_drift": len(schema_drift),
    }
    return {
        "inventory_version": 1,
        "purpose": "Exhaustive schema input for fail-closed policy classification",
        "versions": app_versions,
        "allowed_final_classifications": [
            "managed",
            "conditional",
            "entity",
            "transaction",
            "system",
            "secret",
            "transient",
            "excluded",
            "child-table",
        ],
        "summary": summary,
        "completeness": {
            "missing_scope_sources": missing_scope_sources,
            "missing_fingerprints": missing_fingerprints,
            "managed_entries_without_acceptance": missing_acceptance,
            "schema_drift": schema_drift,
        },
        "doctypes": doctypes,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apps-root",
        type=Path,
        default=Path("/home/frappe/frappe-bench/apps"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", type=Path)
    args = parser.parse_args()

    inventory = build_inventory(args.apps_root, args.scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
    temporary.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(json.dumps(inventory["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
