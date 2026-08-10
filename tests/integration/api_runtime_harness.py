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

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _config() -> dict[str, Any]:
    with (ROOT / "config.yml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


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
            with self.opener.open(request, timeout=30) as raw:
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
            with self.opener.open(request, timeout=30) as raw:
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
    )
    for doctype, filters in residue_queries:
        query = quote(json.dumps(filters))
        residue = client.request(
            "GET",
            f"/api/resource/{quote(doctype, safe='')}?fields=%5B%22name%22%5D&filters={query}&limit_page_length=1",
            expected={200},
        )
        assert residue.data["data"] == [], f"acceptance residue remains in {doctype}"
