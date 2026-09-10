"""Single-tenant system configuration reconciler for Frappe/ERPNext.

``config/config.yaml`` is the desired-state source. Secrets remain environment
references and are never returned by the runtime API or written into Frappe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from yaml.resolver import BaseResolver

CONFIG_VERSION = 3
CONFIG_DIR_ENV = "LETRON_CONFIG_DIR"
CONFIG_STATUS_CACHE_KEY = "letron:system-config:status"
SECRET_REFERENCE_FIELDS = {
    "database.root_password",
    "site.admin_password",
    "email.password",
    "delivery.webhook_secret",
    "delivery.realtime_token",
}
REQUIRED_PATHS = {
    "runtime.environment",
    "runtime.image",
    "runtime.platform",
    "runtime.restart_policy",
    "project.name",
    "project.http_port",
    "integration.app_name",
    "integration.app_path",
    "integration.install_on_site",
    "database.image",
    "database.host",
    "database.port",
    "database.root_user",
    "database.root_password",
    "database.charset",
    "database.collation",
    "database.volume",
    "redis.cache",
    "redis.queue",
    "redis.socketio",
    "redis.cache_image",
    "redis.queue_image",
    "site.name",
    "site.header",
    "site.database_type",
    "site.admin_password",
    "developer.mode",
    "developer.allow_tests",
    "developer.request_timeout",
    "frontend.backend",
    "frontend.websocket",
    "frontend.upload_size",
    "frontend.proxy_timeout",
    "workers.short_command",
    "workers.short_replicas",
    "workers.long_command",
    "workers.scheduler_command",
    "email.enabled",
    "email.host",
    "email.port",
    "email.username",
    "email.password",
    "email.use_tls",
    "storage.sites_volume",
    "storage.logs_volume",
    "storage.redis_queue_volume",
    "storage.backup_volume",
    "backup.enabled",
    "backup.interval_hours",
    "backup.retention_days",
    "backup.with_files",
    "credentials.production_like",
    "delivery.enabled",
    "delivery.webhook_url",
    "delivery.webhook_secret",
    "delivery.webhook_timeout_ms",
    "delivery.realtime_url",
    "delivery.realtime_token",
}
ALLOWED_TOP_LEVEL = {
    "version",
    "erpnext_version",
    "runtime",
    "project",
    "integration",
    "database",
    "redis",
    "site",
    "developer",
    "frontend",
    "workers",
    "email",
    "storage",
    "backup",
    "credentials",
    "delivery",
    "system_settings",
}


class ConfigError(ValueError):
    """Raised when the system configuration is invalid or cannot converge."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ConfigError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[4]


def config_dir() -> Path:
    configured = os.environ.get(CONFIG_DIR_ENV)
    return Path(configured).resolve() if configured else workspace_root() / "config"


def config_path(path: str | Path | None = None) -> Path:
    return Path(path).resolve() if path else config_dir() / "config.yaml"


def policy_path() -> Path:
    return config_dir() / "policy.yaml"


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _value_at(data: Mapping[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise ConfigError(f"Missing required config key: {dotted}")
        current = current[part]
    return current


def _dotenv_path(source: Path) -> Path:
    candidates = (".env.local", ".env")
    if os.environ.get("LETRON_ACCEPTANCE") == "1":
        root = workspace_root()
        for name in candidates:
            candidate = root / name
            if candidate.is_file():
                return candidate
        return root / ".env"
    parent = source.parent
    root = parent.parent if parent.name == "config" else parent
    for name in candidates:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return root / ".env"


def _load_dotenv(source: Path) -> None:
    dotenv = _dotenv_path(source)
    if not dotenv.is_file():
        return
    for number, raw in enumerate(dotenv.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid .env line {number}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "A").isalnum() or key.upper() != key:
            raise ConfigError(f"Invalid .env key on line {number}")
        os.environ.setdefault(key, value)


def _secret_reference(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
        raise ConfigError(f"{field} must be an environment reference like ${{SECRET_NAME}}")
    name = value[2:-1]
    if not name or name.upper() != name or not name.replace("_", "A").isalnum():
        raise ConfigError(f"Invalid environment reference for {field}")
    return name


def _resolve_references(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_references(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_references(item) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        name = value[2:-1]
        resolved = os.environ.get(name)
        if not resolved:
            raise ConfigError(f"Missing required secret environment variable: {name}")
        return resolved
    return value


def load_config(path: str | Path | None = None, *, resolve_secrets: bool = False) -> dict[str, Any]:
    source = config_path(path)
    if not source.is_file():
        raise ConfigError(f"Missing config YAML: {source}")
    try:
        raw = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ConfigError(f"Invalid config YAML: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError("Config YAML root must be a mapping")
    unknown = set(raw) - ALLOWED_TOP_LEVEL
    if unknown:
        raise ConfigError(f"Unsupported top-level config keys: {', '.join(sorted(unknown))}")
    if raw.get("version") != CONFIG_VERSION:
        raise ConfigError(f"Config version must be {CONFIG_VERSION}")
    if not isinstance(raw.get("erpnext_version"), str) or not raw["erpnext_version"]:
        raise ConfigError("erpnext_version must be a non-empty string")
    for dotted in REQUIRED_PATHS:
        value = _value_at(raw, dotted)
        if value is None or value == "":
            raise ConfigError(f"Missing required config key: {dotted}")
    for dotted in SECRET_REFERENCE_FIELDS:
        _secret_reference(_value_at(raw, dotted), dotted)
    settings = raw.get("system_settings")
    if not isinstance(settings, dict):
        raise ConfigError("system_settings must be a mapping")
    if raw["runtime"]["environment"] not in {"local", "production-like"}:
        raise ConfigError("runtime.environment must be local or production-like")
    if raw["site"]["database_type"] != "mariadb":
        raise ConfigError("site.database_type must be mariadb for this deployment")
    if not isinstance(raw["project"]["http_port"], int) or not 1 <= raw["project"]["http_port"] <= 65535:
        raise ConfigError("project.http_port must be an integer from 1 to 65535")
    short_replicas = raw["workers"]["short_replicas"]
    if not isinstance(short_replicas, int) or not 1 <= short_replicas <= 8:
        raise ConfigError("workers.short_replicas must be an integer from 1 to 8")
    for dotted, minimum, maximum in (
        ("backup.interval_hours", 1, 168),
        ("backup.retention_days", 1, 365),
    ):
        value = _value_at(raw, dotted)
        if not isinstance(value, int) or not minimum <= value <= maximum:
            raise ConfigError(f"{dotted} must be an integer from {minimum} to {maximum}")
    if resolve_secrets:
        _load_dotenv(source)
        return _resolve_references(raw)
    return raw


def config_sha256(config: Mapping[str, Any]) -> str:
    encoded = json.dumps(_plain(config), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def dump_config(config: Mapping[str, Any]) -> str:
    return yaml.safe_dump(
        _plain(config), allow_unicode=True, default_flow_style=False, sort_keys=False, width=120
    )


def validate_file(path: str | Path | None = None) -> dict[str, Any]:
    source = config_path(path)
    config = load_config(source)
    return {
        "ok": True,
        "path": str(source),
        "version": config["version"],
        "schema_version": config["version"],
        "scope_version": 1,
        "erpnext_version": config["erpnext_version"],
        "sha256": config_sha256(config),
        "system_settings": len(config["system_settings"]),
    }


def validate_bundle(
    config_source: str | Path | None = None,
    policy_source: str | Path | None = None,
) -> dict[str, Any]:
    """Validate the two deployment sources together without touching runtime state."""

    from letron_api.control.policy import load_policy, policy_sha256

    config = load_config(config_source)
    policy = load_policy(policy_source or policy_path())
    company = policy["bootstrap"]["company"]
    documents = {
        (entry["doctype"], entry["name"]): entry
        for entry in policy["documents"]
        if entry["state"] == "present"
    }
    global_defaults = documents.get(("Global Defaults", "Global Defaults"), {}).get("fields", {})
    expected = {
        "erpnext_version": (config["erpnext_version"], policy["erpnext_version"]),
    }
    if "country" in global_defaults:
        expected["country/global_defaults"] = (company["country"], global_defaults["country"])
    if "default_currency" in global_defaults:
        expected["currency/global_defaults"] = (company["currency"], global_defaults["default_currency"])
    default_company = global_defaults.get("default_company")
    if default_company is not None:
        expected["company/global_defaults"] = (company["name"], default_company)
    mismatches = [name for name, (left, right) in expected.items() if left != right]
    if mismatches:
        raise ConfigError("Config/policy invariant mismatch: " + ", ".join(mismatches))
    return {
        "ok": True,
        "config_sha256": config_sha256(config),
        "policy_sha256": policy_sha256(policy),
        "company": company["name"],
    }


def launcher_environment(path: str | Path | None = None) -> dict[str, str]:
    config = load_config(path, resolve_secrets=True)
    from letron_api.control.policy import load_policy

    policy = load_policy(config_path(path).parent / "policy.yaml")
    company = policy["bootstrap"]["company"]
    if config["credentials"]["production_like"]:
        if config["developer"]["mode"] or config["developer"]["allow_tests"]:
            raise ConfigError("Production-like configuration forbids developer mode and allow_tests")
        forbidden = {"admin", "123", "password", "change-me", "change-me-local-db", "change-me-local-admin"}
        for field in ("database.root_password", "site.admin_password"):
            if str(_value_at(config, field)) in forbidden:
                raise ConfigError(f"Production-like configuration uses a placeholder secret: {field}")
    if config["email"]["enabled"] and (
        config["email"]["host"] == "smtp.example.local"
        or config["email"]["password"] == "change-me"
    ):
        raise ConfigError("SMTP is enabled but still uses placeholder configuration")
    values = {
        "PROJECT_NAME": config["project"]["name"],
        "ERPNEXT_IMAGE": config["runtime"]["image"],
        "PLATFORM": config["runtime"]["platform"],
        "RESTART_POLICY": config["runtime"]["restart_policy"],
        "HTTP_PORT": config["project"]["http_port"],
        "INTEGRATION_APP": config["integration"]["app_name"],
        "INTEGRATION_APP_ENABLED": config["integration"]["install_on_site"],
        "DB_IMAGE": config["database"]["image"],
        "DB_HOST": config["database"]["host"],
        "DB_PORT": config["database"]["port"],
        "DB_ROOT_USER": config["database"]["root_user"],
        "DB_ROOT_PASSWORD": config["database"]["root_password"],
        "DB_CHARSET": config["database"]["charset"],
        "DB_COLLATION": config["database"]["collation"],
        "DB_VOLUME": config["database"]["volume"],
        "REDIS_CACHE": config["redis"]["cache"],
        "REDIS_QUEUE": config["redis"]["queue"],
        "REDIS_SOCKETIO": config["redis"]["socketio"],
        "REDIS_CACHE_IMAGE": config["redis"]["cache_image"],
        "REDIS_QUEUE_IMAGE": config["redis"]["queue_image"],
        "SITE_NAME": config["site"]["name"],
        "SITE_HEADER": config["site"]["header"],
        "ADMIN_PASSWORD": config["site"]["admin_password"],
        "DEVELOPER_MODE": config["developer"]["mode"],
        "ALLOW_TESTS": config["developer"]["allow_tests"],
        "REQUEST_TIMEOUT": config["developer"]["request_timeout"],
        "COUNTRY": company["country"],
        "TIMEZONE": config["system_settings"]["time_zone"],
        "LANGUAGE": config["system_settings"]["language"],
        "CURRENCY": company["currency"],
        "FRONTEND_BACKEND": config["frontend"]["backend"],
        "FRONTEND_WEBSOCKET": config["frontend"]["websocket"],
        "FRONTEND_UPLOAD_SIZE": config["frontend"]["upload_size"],
        "FRONTEND_PROXY_TIMEOUT": config["frontend"]["proxy_timeout"],
        "SHORT_COMMAND": config["workers"]["short_command"],
        "SHORT_WORKER_REPLICAS": config["workers"]["short_replicas"],
        "LONG_COMMAND": config["workers"]["long_command"],
        "SCHEDULER_COMMAND": config["workers"]["scheduler_command"],
        "EMAIL_ENABLED": config["email"]["enabled"],
        "SMTP_HOST": config["email"]["host"],
        "SMTP_PORT": config["email"]["port"],
        "SMTP_USERNAME": config["email"]["username"],
        "SMTP_PASSWORD": config["email"]["password"],
        "SMTP_USE_TLS": config["email"]["use_tls"],
        "SITES_VOLUME": config["storage"]["sites_volume"],
        "LOGS_VOLUME": config["storage"]["logs_volume"],
        "REDIS_QUEUE_VOLUME": config["storage"]["redis_queue_volume"],
        "BACKUP_VOLUME": config["storage"]["backup_volume"],
        "BACKUP_ENABLED": config["backup"]["enabled"],
        "BACKUP_INTERVAL_HOURS": config["backup"]["interval_hours"],
        "BACKUP_RETENTION_DAYS": config["backup"]["retention_days"],
        "BACKUP_WITH_FILES": config["backup"]["with_files"],
        "DELIVERY_ENABLED": config["delivery"]["enabled"],
        "LETRON_WEBHOOK_URL": config["delivery"]["webhook_url"],
        "LETRON_WEBHOOK_SECRET": config["delivery"]["webhook_secret"],
        "LETRON_WEBHOOK_TIMEOUT_MS": config["delivery"]["webhook_timeout_ms"],
        "LETRON_REALTIME_URL": config["delivery"]["realtime_url"],
        "LETRON_REALTIME_TOKEN": config["delivery"]["realtime_token"],
        "LETRON_CONFIG_HOST_DIR": str(config_path(path).parent),
    }
    return {key: str(value) for key, value in values.items()}


def _frappe() -> Any:
    import frappe

    return frappe


def _runtime_erpnext_version() -> str:
    import erpnext

    return str(getattr(erpnext, "__version__", ""))


def _common_desired(config: Mapping[str, Any]) -> dict[str, Any]:
    from letron_api.control.policy import load_policy

    company = load_policy(policy_path())["bootstrap"]["company"]
    return {
        "letron_config_sha256": config_sha256(config),
        "db_host": config["database"]["host"],
        "db_port": config["database"]["port"],
        "redis_cache": f"redis://{config['redis']['cache']}",
        "redis_queue": f"redis://{config['redis']['queue']}",
        "redis_socketio": f"redis://{config['redis']['socketio']}",
        "socketio_port": 9000,
        "developer_mode": config["developer"]["mode"],
        "allow_tests": config["developer"]["allow_tests"],
        "request_timeout": config["developer"]["request_timeout"],
        "country": company["country"],
        "time_zone": config["system_settings"]["time_zone"],
        "lang": config["system_settings"]["language"],
        "currency": company["currency"],
        "chromium_path": "/usr/bin/chromium-headless-shell",
    }


def _common_path() -> Path:
    frappe = _frappe()
    return Path(frappe.get_site_path()).resolve().parent / "common_site_config.json"


def _read_common() -> dict[str, Any]:
    path = _common_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _validate_runtime(config: Mapping[str, Any]) -> None:
    if _runtime_erpnext_version() != config["erpnext_version"]:
        raise ConfigError(
            f"ERPNext version mismatch: YAML={config['erpnext_version']} runtime={_runtime_erpnext_version()}"
        )
    frappe = _frappe()
    meta = frappe.get_meta("System Settings")
    fields = {field.fieldname: field for field in meta.fields if field.fieldname}
    for fieldname in config["system_settings"]:
        field = fields.get(fieldname)
        if field is None:
            raise ConfigError(f"Unknown native field: System Settings.{fieldname}")
        if field.fieldtype in {"Password", "Table", "Table MultiSelect"}:
            raise ConfigError(f"Unsupported managed field: System Settings.{fieldname}")
        if getattr(field, "is_virtual", False):
            raise ConfigError(f"Virtual field cannot be managed: System Settings.{fieldname}")


def plan(path: str | Path | None = None) -> dict[str, Any]:
    config = load_config(path)
    _validate_runtime(config)
    frappe = _frappe()
    changes: list[dict[str, Any]] = []
    common = _read_common()
    for fieldname, desired in _common_desired(config).items():
        if _plain(common.get(fieldname)) != _plain(desired):
            changes.append(
                {
                    "target": "common_site_config.json",
                    "field": fieldname,
                    "current": _plain(common.get(fieldname)),
                    "desired": _plain(desired),
                    "restart_required": True,
                }
            )
    settings = frappe.get_single("System Settings")
    for fieldname, desired in config["system_settings"].items():
        if _plain(settings.get(fieldname)) != _plain(desired):
            changes.append(
                {
                    "target": "System Settings",
                    "field": fieldname,
                    "current": _plain(settings.get(fieldname)),
                    "desired": _plain(desired),
                    "restart_required": False,
                }
            )
    return {
        "ok": not changes,
        "version": config["version"],
        "erpnext_version": config["erpnext_version"],
        "sha256": config_sha256(config),
        "drift_count": len(changes),
        "restart_required": any(item["restart_required"] for item in changes),
        "changes": changes,
    }


@contextmanager
def _applying_config() -> Iterator[None]:
    frappe = _frappe()
    previous = getattr(frappe.flags, "in_letron_config_apply", False)
    frappe.flags.in_letron_config_apply = True
    try:
        yield
    finally:
        frappe.flags.in_letron_config_apply = previous


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def apply(path: str | Path | None = None) -> dict[str, Any]:
    config = load_config(path)
    _validate_runtime(config)
    before = plan(path)
    if not before["changes"]:
        result = {**before, "applied": 0}
        _cache_status(result)
        return result
    frappe = _frappe()
    common_path = _common_path()
    common_before = common_path.read_text(encoding="utf-8") if common_path.is_file() else None
    applied = 0
    try:
        common = _read_common()
        desired_common = _common_desired(config)
        common_changes = {key: value for key, value in desired_common.items() if _plain(common.get(key)) != _plain(value)}
        if common_changes:
            common.update(common_changes)
            _atomic_write(common_path, json.dumps(common, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            applied += len(common_changes)
        with _applying_config():
            settings = frappe.get_single("System Settings")
            changed = False
            for fieldname, desired in config["system_settings"].items():
                if _plain(settings.get(fieldname)) != _plain(desired):
                    settings.set(fieldname, desired)
                    changed = True
                    applied += 1
            if changed:
                settings.flags.ignore_permissions = True
                settings.save(ignore_permissions=True)
        frappe.clear_cache()
        after = plan(path)
        if after["changes"]:
            raise ConfigError(f"Config readback still has {after['drift_count']} drift entries")
        frappe.db.commit()
        result = {**after, "applied": applied, "restart_required": bool(common_changes)}
        _cache_status(result)
        return result
    except Exception:
        frappe.db.rollback()
        if common_before is None:
            common_path.unlink(missing_ok=True)
        else:
            _atomic_write(common_path, common_before)
        raise


def status(path: str | Path | None = None) -> dict[str, Any]:
    try:
        result = plan(path)
        result["status"] = "in-sync" if result["ok"] else "drifted"
        result.pop("changes", None)
        return result
    except Exception as error:  # noqa: BLE001 - health must fail closed
        return {"ok": False, "status": "invalid", "error": type(error).__name__, "message": str(error)}


def bundle_status() -> dict[str, Any]:
    try:
        result = validate_bundle()
        return {**result, "status": "in-sync"}
    except Exception as error:  # noqa: BLE001 - health must fail closed
        return {"ok": False, "status": "invalid", "error": type(error).__name__, "message": str(error)}


def _cache_status(result: Mapping[str, Any]) -> None:
    frappe = _frappe()
    cached = {
        key: result[key]
        for key in ("ok", "version", "erpnext_version", "sha256", "drift_count", "restart_required")
        if key in result
    }
    cached["status"] = "in-sync" if cached.get("ok") else "drifted"
    frappe.cache().set_value(CONFIG_STATUS_CACHE_KEY, cached, expires_in_sec=3600)


def cached_status() -> dict[str, Any]:
    frappe = _frappe()
    cached = frappe.cache().get_value(CONFIG_STATUS_CACHE_KEY)
    if isinstance(cached, dict):
        return cached
    result = status()
    _cache_status(result)
    return result


def sync() -> dict[str, Any]:
    assert_config_directory_writable()
    validate_bundle()
    return apply()


def assert_config_directory_writable() -> None:
    """Prove the container user can perform the same atomic replace used by PUT."""

    directory = config_dir()
    probe = directory / f".letron-write-probe-{os.getpid()}"
    replacement = directory / f".letron-write-probe-{os.getpid()}.replacement"
    try:
        probe.write_text("probe\n", encoding="utf-8", newline="\n")
        replacement.write_text("replacement\n", encoding="utf-8", newline="\n")
        os.replace(replacement, probe)
    except OSError as error:
        raise ConfigError(f"Config directory is not atomically writable: {directory}: {error}") from error
    finally:
        probe.unlink(missing_ok=True)
        replacement.unlink(missing_ok=True)


def audit() -> None:
    _cache_status(status())


def protect_system_settings(doc: Any, method: str | None = None) -> None:
    frappe = _frappe()
    if any(
        getattr(frappe.flags, name, False)
        for name in ("in_install", "in_migrate", "in_patch", "in_letron_config_apply")
    ):
        return
    desired = load_config()["system_settings"]
    before = doc.get_doc_before_save()
    changed = [
        fieldname
        for fieldname in desired
        if before is None or _plain(before.get(fieldname)) != _plain(doc.get(fieldname))
    ]
    if changed:
        frappe.throw(
            "Managed System Settings can only be changed in config/config.yaml: "
            + ", ".join(sorted(changed)),
            exc=frappe.PermissionError,
        )


def acceptance_force_drift() -> None:
    frappe = _frappe()
    if not frappe.conf.get("developer_mode") or not frappe.conf.get("allow_tests"):
        raise ConfigError("Intentional drift is restricted to developer test sites")
    if frappe.session.user != "Administrator":
        raise ConfigError("Intentional drift requires Administrator")
    desired = load_config()["system_settings"]["enable_password_policy"]
    frappe.db.set_single_value("System Settings", "enable_password_policy", 0 if desired else 1)
    frappe.db.commit()


def _main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Validate and materialize Letron system configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--path")
    bundle_parser = subparsers.add_parser("bundle-validate")
    bundle_parser.add_argument("--config")
    bundle_parser.add_argument("--policy")
    env_parser = subparsers.add_parser("env")
    env_parser.add_argument("--path")
    env_parser.add_argument("--format", choices=("json", "posix"), default="json")
    args = parser.parse_args()
    if args.command == "validate":
        print(json.dumps(validate_file(args.path), ensure_ascii=False, sort_keys=True))
    elif args.command == "bundle-validate":
        print(json.dumps(validate_bundle(args.config, args.policy), ensure_ascii=False, sort_keys=True))
    elif args.command == "env":
        environment = launcher_environment(args.path)
        if args.format == "json":
            print(json.dumps(environment, ensure_ascii=False, sort_keys=True))
        else:
            for key, value in environment.items():
                print(f"export {key}={shlex.quote(value)}")
    else:
        raise ConfigError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    _main()
