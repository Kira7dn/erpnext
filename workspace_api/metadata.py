import ast
import json
from collections.abc import Iterable
from pathlib import Path

from .models import DocType, Field, WhitelistedMethod


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def discover_doctypes(roots: Iterable[tuple[str, Path]]) -> list[DocType]:
    result: list[DocType] = []
    for _app, root in roots:
        for path in root.rglob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict) or data.get("doctype") != "DocType" or not data.get("name"):
                continue
            fields = [Field(str(f["fieldname"]), str(f.get("fieldtype", "Data")), f.get("label"), f.get("options"), int(f.get("reqd", 0) or 0))
                      for f in data.get("fields", []) if isinstance(f, dict) and f.get("fieldname")]
            result.append(DocType(str(data["name"]), data.get("module"), str(path), int(data.get("istable", 0) or 0), fields))
    return sorted(result, key=lambda item: item.name.lower())


def discover_whitelisted_methods(roots: Iterable[tuple[str, Path]]) -> list[WhitelistedMethod]:
    result: list[WhitelistedMethod] = []
    for app, root in roots:
        for path in root.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            relative = path.relative_to(root).with_suffix("")
            parts = [p for p in relative.parts if p != "__init__"]
            module = ".".join([app, *parts])
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if _dotted(target) in {"frappe.whitelist", "whitelist"}:
                        result.append(WhitelistedMethod(f"{module}.{node.name}", str(path), node.name, app))
                        break
    return sorted(result, key=lambda item: item.dotted_path)
