# Business Configuration Inventory

This inventory covers the native ERP configuration bundle used by the internal
policy launcher. The bundle currently declares 90 documents in
[`config/policy.yaml`](../config/policy.yaml).

The policy bundle now describes one Holding site with `Letron Holding` as
HoldCo plus six Company subsidiaries. The shared COA and
Function catalog are expanded into Company-specific native Cost Center records
at policy load time; Account trees remain native ERPNext records owned by each
Company. The native `Fiscal Year: 2026` is declared for all seven legal
Companies with the calendar-year boundary `2026-01-01` through `2026-12-31`.
The comparative native `Fiscal Year: 2025` is also declared for the same seven
Companies so prior-year BCTC columns can use ERPNext's native Fiscal Year
lookup.
The native `Finance Book: Consolidation Adjustment` is also declared for the
Holding adjustment workflow.
The shared native `Bank: TP Bank` placeholder is declared once, with one
company-specific `Bank Account` placeholder for each of the seven legal
Companies. Each placeholder links to that Company's native Account `112`; bank
account numbers remain unset until real banking master data is available.
Payment Terms and Payment Terms Templates are shared native masters for all
seven Companies.

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
