"""Durable local consumer used for end-to-end event delivery acceptance."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

DATABASE = Path(os.environ.get("LETRON_CONSUMER_DATABASE", "/data/events.db"))
WEBHOOK_SECRET = os.environ.get("LETRON_WEBHOOK_SECRET", "")
REALTIME_TOKEN = os.environ.get("LETRON_REALTIME_TOKEN", "")
PORT = int(os.environ.get("LETRON_CONSUMER_PORT", "8090"))
LOCK = threading.RLock()
CHANGED = threading.Condition(LOCK)


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def initialize() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                event_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                received_at REAL NOT NULL,
                PRIMARY KEY (event_id, channel),
                FOREIGN KEY (event_id) REFERENCES events(event_id)
            );
            """
        )


def record(body: bytes, channel: str) -> tuple[int, bool]:
    payload = json.loads(body)
    event_id = payload["event_id"]
    canonical = body.decode("utf-8")
    with CHANGED, _connect() as connection:
        existing = connection.execute("SELECT sequence, payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
        if existing and existing["payload"] != canonical:
            raise ValueError("event_id payload conflict")
        if existing:
            sequence = int(existing["sequence"])
            duplicate = True
        else:
            cursor = connection.execute(
                "INSERT INTO events(event_id, payload, created_at) VALUES (?, ?, ?)",
                (event_id, canonical, time.time()),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("consumer event insert did not return a sequence")
            sequence = cursor.lastrowid
            duplicate = False
        connection.execute(
            "INSERT OR IGNORE INTO deliveries(event_id, channel, received_at) VALUES (?, ?, ?)",
            (event_id, channel, time.time()),
        )
        connection.commit()
        CHANGED.notify_all()
    return sequence, duplicate


def realtime_events(after: int, wait_seconds: float) -> tuple[list[dict[str, Any]], int]:
    deadline = time.monotonic() + wait_seconds
    with CHANGED:
        while True:
            with _connect() as connection:
                rows = connection.execute(
                    """
                    SELECT e.sequence, e.payload
                    FROM events e
                    JOIN deliveries d ON d.event_id = e.event_id AND d.channel = 'realtime'
                    WHERE e.sequence > ? ORDER BY e.sequence ASC LIMIT 100
                    """,
                    (after,),
                ).fetchall()
            if rows or time.monotonic() >= deadline:
                events = [{"sequence": int(row["sequence"]), "payload": json.loads(row["payload"])} for row in rows]
                return events, events[-1]["sequence"] if events else after
            CHANGED.wait(timeout=max(0, deadline - time.monotonic()))


class ConsumerHandler(BaseHTTPRequestHandler):
    server_version = "LetronConsumer/1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"consumer {self.address_string()} {format % args}", flush=True)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _bearer_valid(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        return bool(REALTIME_TOKEN) and hmac.compare_digest(supplied, f"Bearer {REALTIME_TOKEN}")

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if not self._bearer_valid():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        query = parse_qs(parsed.query)
        if parsed.path == "/realtime":
            after = max(0, int(query.get("after", ["0"])[0]))
            wait_ms = min(30000, max(0, int(query.get("wait_ms", ["0"])[0])))
            events, cursor = realtime_events(after, wait_ms / 1000)
            self._json(HTTPStatus.OK, {"events": events, "cursor": cursor})
            return
        if parsed.path == "/probe":
            event_id = query.get("event_id", [""])[0]
            with _connect() as connection:
                event = connection.execute("SELECT sequence, payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
                channels = [row[0] for row in connection.execute("SELECT channel FROM deliveries WHERE event_id = ? ORDER BY channel", (event_id,))]
            self._json(
                HTTPStatus.OK,
                {
                    "found": bool(event),
                    "sequence": int(event["sequence"]) if event else None,
                    "payload": json.loads(event["payload"]) if event else None,
                    "channels": channels,
                    "business_effect_count": 1 if event else 0,
                },
            )
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if parsed.path == "/webhook":
            supplied = self.headers.get("X-Letron-Signature", "")
            expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
            if not WEBHOOK_SECRET or not hmac.compare_digest(supplied, expected):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "invalid_signature"})
                return
            channel = "webhook"
        elif parsed.path == "/realtime":
            if not self._bearer_valid():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            channel = "realtime"
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            sequence, duplicate = record(body, channel)
        except (json.JSONDecodeError, KeyError, TypeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_event"})
            return
        except ValueError:
            self._json(HTTPStatus.CONFLICT, {"error": "event_id_conflict"})
            return
        self._json(HTTPStatus.OK, {"acknowledged": True, "duplicate": duplicate, "sequence": sequence})

    def do_DELETE(self) -> None:
        if urlsplit(self.path).path != "/events":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._bearer_valid():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            cleanup = json.loads(self.rfile.read(length))
            event_ids = cleanup.get("event_ids", [])
            prefix = cleanup.get("prefix")
            if not isinstance(event_ids, list) or not all(isinstance(event_id, str) for event_id in event_ids):
                raise TypeError
            if prefix is not None and (not isinstance(prefix, str) or not re.fullmatch(r"ACCEPTANCE-LOCAL-[0-9a-f]{8}-", prefix)):
                raise TypeError
        except (json.JSONDecodeError, KeyError, TypeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_event_ids"})
            return
        with CHANGED, _connect() as connection:
            if prefix:
                event_ids.extend(
                    row[0]
                    for row in connection.execute(
                        "SELECT event_id FROM events WHERE payload LIKE ?",
                        (f"%{prefix}%",),
                    )
                )
            event_ids = list(dict.fromkeys(event_ids))
            for event_id in event_ids:
                connection.execute("DELETE FROM deliveries WHERE event_id = ?", (event_id,))
                connection.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
            connection.commit()
        self._json(HTTPStatus.OK, {"deleted": len(event_ids)})


def main() -> None:
    initialize()
    ThreadingHTTPServer(("0.0.0.0", PORT), ConsumerHandler).serve_forever()


if __name__ == "__main__":
    main()
