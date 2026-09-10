from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def _operation_count(spec: dict[str, Any]) -> int:
    return sum(
        verb in {"get", "post", "put", "patch", "delete"}
        for item in spec["paths"].values()
        for verb in item
    )


def build_control_plane(server_url: str) -> dict[str, Any]:
    error = {
        code: {
            "description": description,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/FrappeError"}}},
        }
        for code, description in {
            "400": "Invalid request",
            "401": "Authentication required",
            "403": "System Manager required",
            "409": "Source hash or immutable bootstrap conflict",
            "417": "YAML, invariant, or native validation failure",
            "500": "Apply and rollback failure",
        }.items()
    }
    response = {"$ref": "#/components/schemas/ConfigurationResponse"}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Letron ERPNext Configuration Control Plane",
            "version": "1.0.0",
            "description": "Administrative fixed-path API. This is not part of the 137-operation business contract.",
        },
        "servers": [{"url": server_url}],
        "security": [{"frappeToken": []}],
        "paths": {
            "/api/method/letron_api.control.config_control.get_configuration": {
                "get": {
                    "operationId": "getConfiguration",
                    "tags": ["Configuration control"],
                    "parameters": [
                        {"$ref": "#/components/parameters/RequestId"},
                        {"name": "kind", "in": "query", "required": True, "schema": {"$ref": "#/components/schemas/ConfigurationKind"}},
                    ],
                    "responses": {"200": {"description": "Current validated YAML source", "content": {"application/json": {"schema": response}}}, **error},
                }
            },
            "/api/method/letron_api.control.config_control.put_configuration": {
                "put": {
                    "operationId": "putConfiguration",
                    "tags": ["Configuration control"],
                    "parameters": [{"$ref": "#/components/parameters/RequestId"}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/PutConfigurationRequest"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "Applied and verified desired state", "content": {"application/json": {"schema": response}}}, **error},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "frappeToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Frappe token authentication: token api_key:api_secret; System Manager required",
                }
            },
            "parameters": {
                "RequestId": {"name": "X-Request-Id", "in": "header", "schema": {"type": "string"}}
            },
            "schemas": {
                "ConfigurationKind": {"type": "string", "enum": ["config", "policy"]},
                "PutConfigurationRequest": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "content", "expected_source_sha256"],
                    "properties": {
                        "kind": {"$ref": "#/components/schemas/ConfigurationKind"},
                        "content": {"type": "string", "maxLength": 2097152, "description": "UTF-8 YAML; resolved secrets are forbidden"},
                        "expected_source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                        "apply_now": {"type": "boolean", "default": True, "description": "False is restricted to developer test sites"},
                    },
                },
                "ConfigurationState": {
                    "type": "object",
                    "required": ["kind", "source_sha256", "state_sha256", "schema_version", "scope_version"],
                    "properties": {
                        "ok": {"type": "boolean"},
                        "kind": {"$ref": "#/components/schemas/ConfigurationKind"},
                        "content": {"type": "string"},
                        "source_sha256": {"type": "string"},
                        "state_sha256": {"type": "string"},
                        "schema_version": {"type": "integer", "minimum": 2, "maximum": 3},
                        "scope_version": {"type": "integer", "const": 1},
                        "completeness": {"type": "object", "additionalProperties": {"type": "integer"}},
                        "applied": {"type": "integer"},
                        "drift_count": {"type": ["integer", "null"]},
                        "restart_required": {"type": "boolean"},
                    },
                },
                "ConfigurationResponse": {
                    "type": "object",
                    "required": ["message"],
                    "properties": {"message": {"$ref": "#/components/schemas/ConfigurationState"}},
                },
                "FrappeError": {
                    "type": "object",
                    "properties": {
                        "exc_type": {"type": "string"},
                        "exception": {"type": "string"},
                        "_server_messages": {"type": "string"},
                        "request_id": {"type": "string"},
                    },
                },
            },
        },
    }


def write_handoff(directory: Path, public_spec: dict[str, Any], control_spec: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    artifacts = {"public": public_spec, "control-plane": control_spec}
    manifest: dict[str, Any] = {"version": 1, "artifacts": {}}
    for name, spec in artifacts.items():
        json_bytes = (json.dumps(spec, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        yaml_bytes = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True).encode("utf-8")
        (directory / f"{name}.json").write_bytes(json_bytes)
        (directory / f"{name}.yaml").write_bytes(yaml_bytes)
        manifest["artifacts"][name] = {
            "operations": _operation_count(spec),
            "json_sha256": hashlib.sha256(json_bytes).hexdigest(),
            "yaml_sha256": hashlib.sha256(yaml_bytes).hexdigest(),
        }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
