"""Provider-neutral validation for the ERP to e-invoice handoff boundary."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

CONTRACT_PATH = Path(__file__).resolve().parents[3] / "contracts" / "einvoice-handoff.yml"
PROVIDER_STATUSES = {"pending", "submitted", "issued", "rejected", "cancelled", "adjusted"}
REQUIRED_SOURCE_FIELDS = {"company", "doctype", "name", "posting_date", "currency", "conversion_rate"}
REQUIRED_PAYLOAD_FIELDS = {
    "seller": {"company", "tax_id", "company_address"},
    "buyer": {"party", "tax_id", "party_address"},
    "lines": {"item_code", "description", "qty", "uom", "rate", "amount"},
    "taxes": {"account_head", "charge_type", "rate", "tax_amount"},
    "totals": {"net_total", "total_taxes_and_charges", "grand_total", "base_grand_total"},
}


class EInvoiceHandoffError(ValueError):
    """Raised when an e-invoice handoff envelope or provider result is invalid."""


def load_contract(path: str | Path | None = None) -> dict[str, Any]:
    source = Path(path) if path else CONTRACT_PATH
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("kind") != "letron-einvoice-handoff-contract":
        raise EInvoiceHandoffError("invalid e-invoice handoff contract")
    return value


def idempotency_key(source: Mapping[str, Any]) -> str:
    missing = REQUIRED_SOURCE_FIELDS - set(source)
    if missing:
        raise EInvoiceHandoffError("source identity is missing: " + ", ".join(sorted(missing)))
    identity = "|".join(str(source[field]) for field in sorted(REQUIRED_SOURCE_FIELDS))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def validate_provider_result(result: Mapping[str, Any]) -> dict[str, Any]:
    missing = {"status", "received_at"} - set(result)
    if missing:
        raise EInvoiceHandoffError("provider result is missing: " + ", ".join(sorted(missing)))
    status = str(result["status"])
    if status not in PROVIDER_STATUSES:
        raise EInvoiceHandoffError(f"unsupported provider status: {status}")
    if status == "issued" and not result.get("provider_invoice_id"):
        raise EInvoiceHandoffError("issued result requires provider_invoice_id")
    if status == "rejected" and not result.get("rejection_code"):
        raise EInvoiceHandoffError("rejected result requires rejection_code")
    return dict(result)


def validate_handoff(source: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the provider-neutral envelope without signing or sending it."""

    key = idempotency_key(source)
    required_sections = {"seller", "buyer", "lines", "taxes", "totals"}
    missing = required_sections - set(payload)
    if missing:
        raise EInvoiceHandoffError("payload is missing sections: " + ", ".join(sorted(missing)))
    for section, fields in REQUIRED_PAYLOAD_FIELDS.items():
        value = payload[section]
        if not isinstance(value, Mapping):
            raise EInvoiceHandoffError(f"payload section must be an object: {section}")
        missing_fields = fields - set(value)
        if missing_fields:
            raise EInvoiceHandoffError(
                f"payload section {section} is missing: {', '.join(sorted(missing_fields))}"
            )
    return {"idempotency_key": key, "source": dict(source), "payload": dict(payload)}
