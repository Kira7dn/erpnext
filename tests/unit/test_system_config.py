from __future__ import annotations

from pathlib import Path

import pytest
from letron_api import system_config

ROOT = Path(__file__).resolve().parents[2]


def test_repository_system_config_is_valid_and_secret_free() -> None:
    config = system_config.load_config()
    validation = system_config.validate_file()

    assert validation["sha256"] == system_config.config_sha256(config)
    assert validation["system_settings"] == 6
    assert config["version"] == 3
    assert config["runtime"]["environment"] == "production-like"
    assert config["credentials"]["production_like"] is True
    assert config["developer"] == {"mode": False, "allow_tests": False, "request_timeout": 120}
    assert config["site"]["database_type"] == "mariadb"
    assert config["backup"] == {
        "enabled": True,
        "interval_hours": 24,
        "retention_days": 14,
        "with_files": True,
    }
    for field in system_config.SECRET_REFERENCE_FIELDS:
        value = system_config._value_at(config, field)
        assert value.startswith("${") and value.endswith("}")


def test_config_resolves_only_exact_environment_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path(system_config.config_path())
    candidate_dir = tmp_path / "config"
    candidate_dir.mkdir()
    candidate = candidate_dir / "config.yaml"
    candidate.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DB_ROOT_PASSWORD=db-secret\n"
        "ADMIN_PASSWORD=admin-secret\n"
        "SMTP_PASSWORD=smtp-secret\n"
        "LETRON_WEBHOOK_SECRET=webhook-secret\n"
        "LETRON_REALTIME_TOKEN=realtime-secret\n",
        encoding="utf-8",
    )
    for name in (
        "DB_ROOT_PASSWORD",
        "ADMIN_PASSWORD",
        "SMTP_PASSWORD",
        "LETRON_WEBHOOK_SECRET",
        "LETRON_REALTIME_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    resolved = system_config.load_config(candidate, resolve_secrets=True)

    assert resolved["database"]["root_password"] == "db-secret"
    assert resolved["delivery"]["realtime_token"] == "realtime-secret"


def test_config_prefers_local_dotenv_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "config" / "config.yaml"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(system_config.config_path().read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".env").write_text(
        "DB_ROOT_PASSWORD=db-secret\n"
        "ADMIN_PASSWORD=admin-secret\n"
        "SMTP_PASSWORD=smtp-secret\n"
        "LETRON_WEBHOOK_SECRET=webhook-secret\n"
        "LETRON_REALTIME_TOKEN=realtime-secret\n"
        "LETRON_WEBHOOK_TIMEOUT_MS=5000\n"
        "LETRON_WEBHOOK_URL=http://default.local/webhook\n"
        "LETRON_REALTIME_URL=http://default.local/realtime\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "DB_ROOT_PASSWORD=db-secret-local\n"
        "ADMIN_PASSWORD=admin-secret-local\n"
        "SMTP_PASSWORD=smtp-secret-local\n"
        "LETRON_WEBHOOK_SECRET=webhook-secret-local\n"
        "LETRON_REALTIME_TOKEN=realtime-secret-local\n",
        encoding="utf-8",
    )
    for name in (
        "DB_ROOT_PASSWORD",
        "ADMIN_PASSWORD",
        "SMTP_PASSWORD",
        "LETRON_WEBHOOK_SECRET",
        "LETRON_REALTIME_TOKEN",
        "LETRON_WEBHOOK_TIMEOUT_MS",
        "LETRON_WEBHOOK_URL",
        "LETRON_REALTIME_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    resolved = system_config.load_config(source, resolve_secrets=True)

    assert resolved["database"]["root_password"] == "db-secret-local"
    assert resolved["site"]["admin_password"] == "admin-secret-local"
    assert resolved["email"]["password"] == "smtp-secret-local"
    assert resolved["delivery"]["webhook_secret"] == "webhook-secret-local"
    assert resolved["delivery"]["realtime_token"] == "realtime-secret-local"


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("version: 3", "Duplicate YAML key"),
        ("root_password: plaintext", "must be an environment reference"),
        ("environment: unknown", "must be local or production-like"),
    ],
)
def test_invalid_system_config_fails_closed(
    tmp_path: Path, replacement: str, message: str
) -> None:
    content = system_config.config_path().read_text(encoding="utf-8")
    if replacement == "version: 3":
        content = "version: 3\n" + content
    elif replacement.startswith("root_password"):
        content = content.replace("root_password: ${DB_ROOT_PASSWORD}", replacement)
    else:
        content = content.replace("environment: production-like", replacement)
    candidate = tmp_path / "config.yaml"
    candidate.write_text(content, encoding="utf-8")

    with pytest.raises(system_config.ConfigError, match=message):
        system_config.load_config(candidate)


def test_missing_secret_fails_only_when_materializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "config.yaml"
    candidate.write_text(system_config.config_path().read_text(encoding="utf-8"), encoding="utf-8")
    for name in (
        "DB_ROOT_PASSWORD",
        "ADMIN_PASSWORD",
        "SMTP_PASSWORD",
        "LETRON_WEBHOOK_SECRET",
        "LETRON_REALTIME_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)

    assert system_config.load_config(candidate)["version"] == 3
    with pytest.raises(system_config.ConfigError, match="Missing required secret"):
        system_config.load_config(candidate, resolve_secrets=True)


def test_short_worker_replica_count_is_bounded(tmp_path: Path) -> None:
    candidate = tmp_path / "config.yaml"
    content = system_config.config_path().read_text(encoding="utf-8")
    candidate.write_text(content.replace("short_replicas: 2", "short_replicas: 0"), encoding="utf-8")

    with pytest.raises(system_config.ConfigError, match="short_replicas"):
        system_config.load_config(candidate)


def test_repository_config_and_policy_invariants_match() -> None:
    result = system_config.validate_bundle()

    assert result["ok"] is True
    assert result["company"] == "Letron Việt Nam"


def test_cross_file_invariants_fail_closed(tmp_path: Path) -> None:
    candidate = tmp_path / "config.yaml"
    content = system_config.config_path().read_text(encoding="utf-8")
    candidate.write_text(content, encoding="utf-8")

    policy_path = tmp_path / "policy.yaml"
    policy_content = system_config.policy_path().read_text(encoding="utf-8")
    policy_path.write_text(policy_content.replace("country: Vietnam", "country: Singapore", 1), encoding="utf-8")
    with pytest.raises(system_config.ConfigError, match="country/global_defaults"):
        system_config.validate_bundle(candidate, policy_path)


def test_launchers_use_only_the_two_fixed_yaml_sources() -> None:
    powershell = (ROOT / "docker-start.ps1").read_text(encoding="utf-8")
    bash = (ROOT / "erpctl").read_text(encoding="utf-8")

    assert "[string]$ConfigPath" not in powershell
    assert "[switch]$ValidateOnly" not in powershell
    assert "$configPath = Join-Path $root 'config/config.yaml'" in powershell
    assert "$policyPath = Join-Path $root 'config/policy.yaml'" in powershell
    assert 'CONFIG="$ROOT/config/config.yaml"' in bash
    assert 'POLICY="$ROOT/config/policy.yaml"' in bash

    for content, environment_marker in (
        (powershell, "$environmentJson ="),
        (bash, 'eval "$(uv run python'),
    ):
        assert content.index("config-validate") < content.index(environment_marker)
        assert content.index("policy-validate") < content.index(environment_marker)


def test_production_compose_has_no_acceptance_overlay_and_has_backup() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "event-consumer" not in compose
    assert "  backup-init:" in compose
    assert "  backup:" in compose
    assert "  backup-verify:" in compose
    assert "bench --site \"$${SITE_NAME}\" backup" in compose
    assert 'staging="/home/frappe/backups/.staging"' in compose
    assert 'gzip -t "$${db_backup}"' in compose
    assert 'if gzip -t "$${candidate}"' in compose


def test_default_launchers_wait_for_readiness() -> None:
    powershell = (ROOT / "docker-start.ps1").read_text(encoding="utf-8")
    bash = (ROOT / "erpctl").read_text(encoding="utf-8")

    assert "AddSeconds(180)" in powershell
    assert powershell.count("Invoke-Readiness") >= 4
    assert "SECONDS + 180" in bash
    assert bash.count("readiness") >= 4
