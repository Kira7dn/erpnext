"""Small HTTP harness used by the Docker integration acceptance tests.

The harness deliberately uses only the standard library so it can run from the
workspace venv without installing an ERPNext client.  It never logs auth
headers or full response bodies.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener

from letron_api.system_config import load_config

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
    delivery = config["delivery"]
    values = {
        "LETRON_DELIVERY_ENABLED": delivery["enabled"],
        "LETRON_WEBHOOK_URL": delivery["webhook_url"],
        "LETRON_WEBHOOK_SECRET": delivery["webhook_secret"],
        "LETRON_WEBHOOK_TIMEOUT_MS": delivery["webhook_timeout_ms"],
        "LETRON_REALTIME_URL": delivery["realtime_url"],
        "LETRON_REALTIME_TOKEN": delivery["realtime_token"],
        "LETRON_CONSUMER_PORT": os.environ.get("LETRON_CONSUMER_PORT", "8091"),
    }
    for key, value in values.items():
        os.environ.setdefault(key, str(value))
    return config


def cleanup_consumer_events(prefix: str, event_ids: list[str] | None = None) -> None:
    """Delete one run's durable consumer events and require a stable zero."""

    if str(os.environ.get("LETRON_DELIVERY_ENABLED", "false")).lower() not in {"1", "true", "yes"}:
        return
    realtime_url = os.environ.get("LETRON_REALTIME_URL")
    realtime_token = os.environ.get("LETRON_REALTIME_TOKEN")
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
        self.base = f"http://127.0.0.1:{config['project']['http_port']}"
        self.timeout = int(config["developer"]["request_timeout"])
        self.username = "Administrator"
        self.password = os.environ.get("LETRON_ACCEPTANCE_ADMIN_PASSWORD") or config["site"]["admin_password"]
        self.cookies = CookieJar()
        self.opener = build_opener(__import__("urllib.request", fromlist=["HTTPCookieProcessor"]).HTTPCookieProcessor(self.cookies))
        self.evidence: list[dict[str, Any]] = []
        self.authorization: str | None = None

    def write_evidence(self) -> None:
        path = ROOT / ".cache" / "integration-runtime-evidence.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"runtime": self.base, "requests": self.evidence}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: set[int] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        request_id = (headers or {}).get("X-Request-Id") or f"acceptance-{uuid.uuid4()}"
        request_headers = {"Accept": "application/json", "X-Request-Id": request_id, **(headers or {})}
        if self.authorization:
            request_headers["Authorization"] = self.authorization
        body = None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = Request(self.base + path, data=body, headers=request_headers, method=method)
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

    def upload(self, file_name: str, content: bytes, *, expected: set[int] | None = None) -> Response:
        boundary = f"----letron-acceptance-{uuid.uuid4().hex}"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        request_id = f"acceptance-{uuid.uuid4()}"
        headers = {
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Request-Id": request_id,
        }
        if self.authorization:
            headers["Authorization"] = self.authorization
        request = Request(self.base + "/api/method/upload_file", data=body, headers=headers, method="POST")
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
        self.evidence.append({"method": "POST", "path": "/api/method/upload_file", "status": status, "request_id": actual_request_id, "payload": _summary(data)})
        if expected is not None and status not in expected:
            raise AssertionError(f"upload_file: expected {expected}, got {status}: {_summary(data)}")
        return Response(status, response_headers, data, actual_request_id)

    def login(self) -> None:
        response = self.request("POST", "/api/method/login", {"usr": self.username, "pwd": self.password}, expected={200})
        if not isinstance(response.data, dict) or not response.data.get("message"):
            raise RuntimeUnavailable("Administrator login did not establish a Frappe session")

    def document(self, method: str, doctype: str, name: str | None = None, payload: dict[str, Any] | None = None, **kwargs: Any) -> Response:
        path = "/api/resource/" + quote(doctype, safe="")
        if name:
            path += "/" + quote(name, safe="")
        return self.request(method, path, payload, **kwargs)

    def public(self, method: str, path: str, payload: dict[str, Any] | None = None, **kwargs: Any) -> Response:
        return self.request(method, path, payload, **kwargs)

    def health_and_login(self) -> None:
        health = self.request("GET", "/api/method/letron_api.api.health", expected={200})
        if not isinstance(health.data, dict) or health.data.get("message", {}).get("ok") is not True:
            raise RuntimeUnavailable("health endpoint did not return ok=true")
        self.login()

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
    fallback = client.request("POST", "/api/method/letron_api.api.acceptance_cleanup", {"prefix": prefix}, expected={200})
    cleanup_result = fallback.data.get("message", {}) if isinstance(fallback.data, dict) else {}
    endpoint_failures = cleanup_result.get("failures", [])
    if endpoint_failures:
        raise AssertionError("fixture cleanup failed: " + ", ".join(endpoint_failures))
    for doctype, name in created:
        client.document("GET", doctype, name, expected={404})
    if failures and not cleanup_result.get("deleted"):
        raise AssertionError("fixture cleanup fallback removed nothing: " + ", ".join(failures))

    residue_queries = (
        ("File", [["file_name", "like", f"{prefix}%"]]),
        ("Letron Event Outbox", [["payload", "like", f"%{prefix}%"]]),
        ("Bank", [["name", "like", f"{prefix}%"]]),
        ("Bank Account", [["name", "like", f"{prefix}%"]]),
        ("Mode of Payment", [["name", "like", f"{prefix}%"]]),
        ("Cost Center", [["company", "like", f"{prefix}%"]]),
        ("Journal Entry", [["company", "like", f"{prefix}%"]]),
        ("Payment Request", [["company", "like", f"{prefix}%"]]),
        ("Stock Ledger Entry", [["company", "like", f"{prefix}%"]]),
        ("GL Entry", [["company", "like", f"{prefix}%"]]),
        ("Payment Ledger Entry", [["company", "like", f"{prefix}%"]]),
        ("Stock Reconciliation", [["name", "like", f"{prefix}%"]]),
        ("Serial No", [["name", "like", f"{prefix}%"]]),
        ("Batch", [["name", "like", f"{prefix}%"]]),
        ("Quality Inspection", [["name", "like", f"{prefix}%"]]),
        ("Pick List", [["name", "like", f"{prefix}%"]]),
        ("Shipment", [["name", "like", f"{prefix}%"]]),
        ("Landed Cost Voucher", [["name", "like", f"{prefix}%"]]),
        ("Stock Reservation Entry", [["name", "like", f"{prefix}%"]]),
    )
    for doctype, filters in residue_queries:
        query = quote(json.dumps(filters))
        residue = client.request(
            "GET",
            f"/api/resource/{quote(doctype, safe='')}?fields=%5B%22name%22%5D&filters={query}&limit_page_length=1",
            expected={200},
        )
        assert residue.data["data"] == [], f"acceptance residue remains in {doctype}"
