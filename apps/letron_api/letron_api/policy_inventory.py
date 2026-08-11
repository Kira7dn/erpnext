"""Generate an exhaustive, machine-readable ERPNext/Frappe DocType inventory.

This is deliberately broader than the policy wrapper.  Every native DocType
schema is retained verbatim so that classification can fail closed instead of
silently losing a field, default, false value, child table, permission, or
future upstream addition.
"""

from __future__ import annotations

import argparse
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


def build_inventory(apps_root: Path) -> dict[str, Any]:
    doctypes: list[dict[str, Any]] = []
    app_versions: dict[str, str | None] = {}
    field_count = 0

    for app_name in APP_NAMES:
        app_root = apps_root / app_name
        if not app_root.exists():
            raise FileNotFoundError(f"Installed app source not found: {app_root}")
        app_versions[app_name] = _version(app_root, app_name)
        pattern_root = app_root / app_name
        for source in sorted(pattern_root.glob("**/doctype/*/*.json")):
            schema = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(schema, dict):
                continue
            if schema.get("doctype") != "DocType" or not schema.get("name"):
                continue
            reasons = _candidate_reasons(schema)
            classification = "child-table" if schema.get("istable") else "unclassified"
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
                    "schema": schema,
                }
            )

    doctypes.sort(key=lambda item: (item["app"], item["schema"]["name"]))
    summary = {
        "doctypes": len(doctypes),
        "fields": field_count,
        "policy_candidates": sum(
            item["classification"] == "policy-candidate" for item in doctypes
        ),
        "child_tables": sum(item["classification"] == "child-table" for item in doctypes),
        "unclassified": sum(item["classification"] == "unclassified" for item in doctypes),
    }
    return {
        "inventory_version": 1,
        "purpose": "Exhaustive schema input for fail-closed policy classification",
        "versions": app_versions,
        "allowed_final_classifications": [
            "policy",
            "entity",
            "transaction",
            "system",
            "secret",
            "transient",
            "child-table",
        ],
        "summary": summary,
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
    args = parser.parse_args()

    inventory = build_inventory(args.apps_root)
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
