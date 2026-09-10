"""Frappe scheduler trigger for the Next.js supplier approval orchestrator."""

from __future__ import annotations

import os
import json
from pathlib import Path

import requests


def process_supplier_portal_deadlines() -> None:
    config_dir = Path(os.environ.get("LETRON_CONFIG_DIR", "config"))
    try:
        settings = json.loads((config_dir / "supplier_portal.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    base_url = (str(settings.get("next_base_url") or "")).rstrip("/")
    secret = os.environ.get("LETRON_SUPPLIER_PORTAL_CRON_SECRET") or ""
    if not base_url or not secret:
        return
    response = requests.post(
        f"{base_url}/api/internal/supplier-portal/deadlines",
        headers={"X-Letron-Cron-Secret": secret, "Accept": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
