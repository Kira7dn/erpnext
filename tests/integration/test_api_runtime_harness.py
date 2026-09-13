"""Small HTTP harness used by the Docker integration acceptance tests.

The harness deliberately uses only the standard library so it can run from the
workspace venv without installing an ERPNext client.  It never logs auth
headers or full response bodies.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote
from urllib.request import Request, build_opener

from letron_api.contract_runtime import validate_request
from letron_api.control.system_config import load_config

ROOT = Path(__file__).resolve().parents[2]


def _config() -> dict[str, Any]:
    acceptance_dir = os.environ.get("LETRON_ACCEPTANCE_CONFIG_DIR")
    if acceptance_dir:
        acceptance_root = Path(acceptance_dir)
        source = acceptance_root / "config.yaml"
        if not source.is_file():
            source = acceptance_root / "config.acceptance.yaml"
    else:
        source = ROOT / "config" / "config.yaml"
    config = load_config(source, resolve_secrets=True)
    return config


def cleanup_consumer_events(prefix: str, event_ids: list[str] | None = None) -> None:
    """Delete one run's durable consumer events and require a stable zero."""

    delivery = _config()["delivery"]
    if not delivery["enabled"]:
        return
    realtime_url = delivery["realtime_url"]
    realtime_token = delivery["realtime_token"]
    if not realtime_url or not realtime_token:
        return
    port = os.environ.get("LETRON_CONSUMER_PORT", "8091")
    events_url = realtime_url.replace("http://event-consumer:8090", f"http://127.0.0.1:{port}").replace(
        "/realtime", "/events"
    )
    headers = {"Authorization": f"Bearer {realtime_token}", "Content-Type": "application/json"}

    def delete_events(ids: list[str]) -> int:
        request = Request(
            events_url,
            data=json.dumps({"event_ids": ids, "prefix": prefix}).encode(),
            method="DELETE",
            headers=headers,
        )
        try:
            with build_opener().open(request, timeout=30) as response:
                status = response.status
                payload = json.loads(response.read().decode())
        except HTTPError as error:
            status = error.code
            payload = json.loads(error.read().decode())
        assert status == 200, f"consumer cleanup failed for {prefix}: {status} {payload}"
        return int(payload["deleted"])

    time.sleep(2)
    delete_events(event_ids or [])
    stable_zero_polls = 0
    for _ in range(60):
        time.sleep(0.5)
        stable_zero_polls = stable_zero_polls + 1 if delete_events([]) == 0 else 0
        if stable_zero_polls >= 5:
            return
    raise AssertionError("consumer acceptance residue did not remain zero for five consecutive polls")


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    data: Any
    request_id: str | None


class RuntimeUnavailable(RuntimeError):
    """Raised when acceptance cannot safely run against a live site."""


def retryable_status(status: int) -> bool:
    """Only transient transport/server responses may be retried."""
    return status in {408, 429} or status >= 500


class ApiClient:
    def __init__(self) -> None:
        config = _config()
        self.backend_base = f"http://127.0.0.1:{config['project']['http_port']}"
        self.transport = "gateway"
        self.gateway_base = os.environ.get("LETRON_AUTH_BASE_URL", "").rstrip("/")
        self.base = self.gateway_base
        self.timeout = min(int(config["developer"]["request_timeout"]), 60)
        self.username: str | None = None
        self.password: str | None = None
        self.cookies = CookieJar()
        self.opener = build_opener(__import__("urllib.request", fromlist=["HTTPCookieProcessor"]).HTTPCookieProcessor(self.cookies))
        self.evidence: list[dict[str, Any]] = []
        self.authorization: str | None = None
        self.authenticated = False

    def write_evidence(self) -> None:
        path = ROOT / ".cache" / "integration-runtime-evidence.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "backend_runtime": self.backend_base,
                    "gateway_runtime": self.gateway_base or None,
                    "transport": self.transport,
                    "requests": self.evidence,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: set[int] | None = None,
        headers: dict[str, str] | None = None,
        transport: str = "backend",
    ) -> Response:
        if transport not in {"backend", "gateway"}:
            raise RuntimeUnavailable(f"Unsupported integration transport: {transport}")
        base = self.backend_base if transport == "backend" else self.gateway_base
        if not base:
            raise RuntimeUnavailable(
                "Gateway integration requires LETRON_AUTH_BASE_URL"
            )
        request_id = (headers or {}).get("X-Request-Id") or f"acceptance-{uuid.uuid4()}"
        request_headers = {"Accept": "application/json", "X-Request-Id": request_id, **(headers or {})}
        if self.authorization:
            request_headers["Authorization"] = self.authorization
        if transport == "gateway" and self.authenticated:
            if "Authorization" not in request_headers:
                secret = os.environ.get("LETRON_INTERNAL_API_SECRET", "").strip()
                if not secret:
                    raise RuntimeUnavailable("Gateway integration requires LETRON_INTERNAL_API_SECRET")
                request_headers["Authorization"] = f"Bearer {secret}"
        elif path.startswith(("/api/resource/", "/api/method/")):
            request_headers.update(self._control_plane_headers(method, path, request_id))
        body = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
            if transport == "gateway" and path.startswith("/api/v1/") and method.upper() in {"POST", "PUT", "PATCH"}:
                try:
                    validate_request(method, path, body)
                except ValueError as error:
                    # Negative contract tests must still reach the live Gateway
                    # so their HTTP status and envelope remain integration-tested.
                    if not expected or not expected.intersection({400, 417}):
                        raise AssertionError(f"local generated-contract validation failed for {method} {path}: {error}") from error
        gateway_prefix = "" if path.startswith("/api/internal/") else "/api/gateway"
        target = base + (gateway_prefix if transport == "gateway" else "") + path
        request = Request(target, data=body, headers=request_headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as raw:
                status = raw.status
                response_headers = {key.lower(): value for key, value in raw.headers.items()}
                content = raw.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            status = error.code
            response_headers = {key.lower(): value for key, value in error.headers.items()}
            content = error.read().decode("utf-8", errors="replace")
        except (URLError, TimeoutError, OSError) as error:
            raise RuntimeUnavailable(f"HTTP runtime unavailable for {method} {path}: {error}") from error
        try:
            data: Any = json.loads(content) if content else None
        except json.JSONDecodeError:
            data = {"text": content[:240]}
        actual_request_id = response_headers.get("x-request-id")
        self.evidence.append({"method": method, "path": path, "status": status, "request_id": actual_request_id, "payload": _summary(data)})
        if expected is not None and status not in expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {_summary(data)}")
        return Response(status, response_headers, data, actual_request_id)

    def upload(self, file_name: str, content: bytes, *, attached_to_doctype: str, attached_to_name: str, expected: set[int] | None = None) -> Response:
        boundary = f"----letron-acceptance-{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        ).encode() + content + (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="attached_to_doctype"\r\n\r\n{attached_to_doctype}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="attached_to_name"\r\n\r\n{attached_to_name}\r\n'
            f"--{boundary}--\r\n"
        ).encode()
        request_id = f"acceptance-{uuid.uuid4()}"
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Request-Id": request_id,
        }
        if self.authorization:
            headers["Authorization"] = self.authorization
        path = "/api/v1/files/attachments"
        if self.transport == "gateway" and self.authenticated and "Authorization" not in headers:
            secret = os.environ.get("LETRON_INTERNAL_API_SECRET", "").strip()
            if not secret:
                raise RuntimeUnavailable("Gateway integration requires LETRON_INTERNAL_API_SECRET")
            headers["Authorization"] = f"Bearer {secret}"
        upload_base = self.gateway_base if self.transport == "gateway" else self.backend_base
        if not upload_base:
            raise RuntimeUnavailable("Gateway upload requires a configured Gateway base URL")
        upload_prefix = "/api/gateway" if self.transport == "gateway" else ""
        request = Request(upload_base + upload_prefix + path, data=body, headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=self.timeout) as raw:
                status = raw.status
                response_headers = {key.lower(): value for key, value in raw.headers.items()}
                data = json.loads(raw.read().decode("utf-8"))
        except HTTPError as error:
            status = error.code
            response_headers = {key.lower(): value for key, value in error.headers.items()}
            data = json.loads(error.read().decode("utf-8", errors="replace"))
        actual_request_id = response_headers.get("x-request-id")
        self.evidence.append({"method": "POST", "path": path, "status": status, "request_id": actual_request_id, "payload": _summary(data)})
        if expected is not None and status not in expected:
            raise AssertionError(f"attachment upload: expected {expected}, got {status}: {_summary(data)}")
        return Response(status, response_headers, data, actual_request_id)

    def authenticate(self) -> None:
        """Mark this client as an integration caller using the existing secret."""
        if not os.environ.get("LETRON_INTERNAL_API_SECRET", "").strip():
            raise RuntimeUnavailable("Integration requires LETRON_INTERNAL_API_SECRET")
        self.authenticated = True

    def login(self) -> None:
        """Create a native Frappe session for a deliberately restricted test user."""
        if not self.username or not self.password:
            raise RuntimeUnavailable("Native permission test requires an explicit test user password")
        response = self.request(
            "POST",
            "/api/method/login",
            {"usr": self.username, "pwd": self.password},
            expected={200},
        )
        if not isinstance(response.data, dict) or not response.data.get("message"):
            raise RuntimeUnavailable("Frappe test-user login did not establish a session")

    def document(self, method: str, doctype: str, name: str | None = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> Response:
        path = "/api/resource/" + quote(doctype, safe="")
        if name:
            path += "/" + quote(name, safe="")
        return self.request(method, path, payload, **kwargs)

    def _gateway_app_for_path(self, path: str) -> str:
        if path.startswith("/api/v1/assets/"):
            return "assets"
        if path.startswith("/api/v1/accounts/"):
            return "accounts"
        return "purchase"

    def public(self, method: str, path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> Response:
        return self.request(method, path, payload, transport=self.transport, **kwargs)

    def _control_plane_headers(self, method: str, path: str, request_id: str) -> dict[str, str]:
        secret = os.environ.get("LETRON_INTERNAL_API_SECRET", "").strip()
        if not secret:
            raise RuntimeUnavailable("Native fixture API requires LETRON_INTERNAL_API_SECRET")
        timestamp = str(int(time.time()))
        expires_at = str(int(timestamp) + 60)
        signed_path = unquote(path.split("?", 1)[0])
        payload = f"{timestamp}.{expires_at}.{method}.{signed_path}.{request_id}"
        signature = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "X-Letron-Control-Timestamp": timestamp,
            "X-Letron-Control-Expires-At": expires_at,
            "X-Letron-Control-Request-Id": request_id,
            "X-Letron-Control-Signature": signature,
        }

    def health_and_login(self) -> None:
        health = self.request("GET", "/api/method/letron_api.control.api.health", expected={200})
        if not isinstance(health.data, dict) or health.data.get("message", {}).get("ok") is not True:
            raise RuntimeUnavailable("health endpoint did not return ok=true")
        self.authenticate()

    def request_with_retry(self, method: str, path: str, payload: dict[str, Any] | None = None, *, attempts: int = 3, **kwargs: Any) -> Response:
        """Bounded retry for transient responses; never retry 4xx business errors."""
        if attempts < 1 or attempts > 3:
            raise ValueError("attempts must be between 1 and 3")
        expected = kwargs.pop("expected", None)
        for attempt in range(attempts):
            try:
                response = self.request(method, path, payload, expected=None, **kwargs)
            except RuntimeUnavailable:
                if attempt + 1 == attempts:
                    raise
                time.sleep(0.1 * (attempt + 1))
                continue
            if retryable_status(response.status) and attempt + 1 < attempts:
                time.sleep(0.1 * (attempt + 1))
                continue
            if expected is not None and response.status not in expected:
                raise AssertionError(f"{method} {path}: expected {expected}, got {response.status}")
            return response
        raise AssertionError("retry loop ended without a response")

    def write_with_reconciliation(self, method: str, path: str, payload: dict[str, Any], reconcile_path: str, *, attempts: int = 3, **kwargs: Any) -> Response:
        """Retry a write, then read its known resource if transport stays uncertain."""
        try:
            return self.request_with_retry(method, path, payload, attempts=attempts, **kwargs)
        except RuntimeUnavailable:
            return self.reconcile(reconcile_path, expected={200, 404})

    def reconcile(self, path: str, *, expected: set[int] | None = None) -> Response:
        """Read the resource after an uncertain write outcome."""
        return self.request("GET", path, expected=expected or {200, 404})


def _summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _summary(item) for key, item in value.items() if key not in {"password", "api_secret", "api_key", "token"}}
    if isinstance(value, list):
        return [_summary(item) for item in value[:3]]
    if isinstance(value, str):
        return value[:240]
    return value


def response_data(response: Response) -> dict[str, Any]:
    data = None
    if isinstance(response.data, dict):
        data = response.data.get("data") or response.data.get("message")
    if not isinstance(data, dict):
        raise TypeError(f"response has no document data: {_summary(response.data)}")
    return data


def create_or_reuse(client: ApiClient, doctype: str, payload: dict[str, Any], created: list[tuple[str, str]] | None = None) -> str:
    name = payload.get("name") or payload.get("item_code")
    if name:
        existing = client.document("GET", doctype, name, expected={200, 404})
        if existing.status == 200:
            return response_data(existing)["name"]
    result = response_data(client.document("POST", doctype, payload=payload, expected={200}))["name"]
    if created is not None:
        created.append((doctype, result))
    return result


def cleanup(client: ApiClient, created: list[tuple[str, str]], prefix: str) -> None:
    """Fail closed if a document created by this run cannot be removed."""
    failures: list[str] = []
    for doctype, name in reversed(created):
        try:
            client.document("DELETE", doctype, name, expected={200, 202, 404})
        except (AssertionError, RuntimeUnavailable):
            failures.append(f"{doctype}:{name}")
    # Always run the scoped teardown endpoint. Normal document deletion does
    # not remove durable outbox rows, so using this only as a fallback leaves
    # acceptance evidence behind after an otherwise successful run.
    fallback = client.request(
        "POST",
        f"/api/method/letron_api.control.api.acceptance_cleanup?prefix={quote(prefix, safe='')}",
        expected={200},
    )
    cleanup_result = fallback.data.get("message", {}) if isinstance(fallback.data, dict) else {}
    endpoint_failures = cleanup_result.get("failures", [])
    if endpoint_failures:
        raise AssertionError("fixture cleanup failed: " + ", ".join(endpoint_failures))
    for doctype, name in created:
        client.document("GET", doctype, name, expected={404})
    if failures and not cleanup_result.get("deleted"):
        raise AssertionError("fixture cleanup fallback removed nothing: " + ", ".join(failures))

