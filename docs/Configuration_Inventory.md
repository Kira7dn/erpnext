# Business Configuration Inventory

This inventory covers the native ERP configuration bundle used by the internal
policy launcher. The bundle currently declares 28 documents in
[`config/policy.yaml`](../config/policy.yaml).

The following single-DocType metadata files are in scope for the bundle:

- `accounts_settings.json`
- `bank_clearance.json`
- `bank_reconciliation_tool.json`
- `bisect_accounting_statements.json`
- `buying_settings.json`
- `chart_of_accounts_importer.json`
- `currency_exchange_settings.json`
- `delivery_settings.json`
- `global_defaults.json`
- `item_variant_settings.json`
- `ledger_health_monitor.json`
- `opening_invoice_creation_tool.json`
- `payment_reconciliation.json`
- `pegged_currencies.json`
- `quick_stock_balance.json`
- `selling_settings.json`
- `sms_center.json`
- `stock_reposting_settings.json`
- `stock_settings.json`

Dynamic OpenAPI RBAC `Custom DocPerm` rows whose role starts with
`Letron Policy - ` are owned by Global Portal and are intentionally excluded
from this native configuration inventory.
