# Inventory policy ERPNext trong phạm vi sản phẩm

## 1. Mục đích và phạm vi

Tài liệu này là SOT duy nhất cho classification và tiến độ Phase 8. Inventory
được giới hạn theo product scope hiện hành, gồm:

- module public: Accounts, Buying, Contacts, Selling và Stock;
- policy Frappe dùng chung tác động trực tiếp tới resource của các module trên;
- Company bootstrap, Chart of Accounts template và regional fixture cần để dựng
  tenant Việt Nam.

CRM chỉ được thêm khi Phase 10 bắt đầu và phải mở rộng inventory trước khi public
contract CRM được công bố. Manufacturing, POS, Subscription, Budget,
Assets/Maintenance, Projects và Support nằm ngoài product scope hiện tại; chúng
không được tính vào `unknown` và không được materialize vào tenant.

Trạng thái 2026-08-12:

| Gate | Trạng thái |
|---|---|
| Runtime foundation | `COMPLETE` cho baseline 28 document native |
| Boundary migration | `COMPLETE` |
| Inventory closure trong phạm vi | `COMPLETE` — scanner `unknown=0`, `unclassified=0` |
| Typed native coverage | `COMPLETE` — 56 managed/conditional source có builder và acceptance mapping |
| Full round-trip acceptance | `COMPLETE` — structural/apply/assets/effect/failure matrix pass |
| Phase 8 host signature | `WINDOWS_DOCKER` — Ubuntu không thuộc gate Phase 8 |

## 2. Boundary và classification

| Loại | Owner/SOT |
|---|---|
| System/runtime | `config/config.yaml` |
| Company bootstrap, country, currency, business policy | `config/policy.yaml` |
| Secret | `.env` hoặc secret store |
| User/Employee/API key/assignment theo cá nhân | Identity API và ERPNext DB |
| Entity/master/transaction/ledger | Business API và ERPNext DB |
| Executable customization/migration | Source và fixture của `letron_api` |
| Generated metadata/catalog | Artifact, không phải SOT |

Mỗi source trong phạm vi phải có đúng một classification:

- `managed`: desired state bắt buộc nằm trong `policy.yaml`;
- `conditional`: chỉ managed khi capability tương ứng được bật;
- `entity`: dữ liệu có lifecycle qua API/DB;
- `secret`: YAML chỉ giữ environment reference, không giữ giá trị thật;
- `transient`: input/result theo phiên, không export;
- `excluded`: không quản lý bằng YAML và có lý do cụ thể.

`unknown` là lỗi completeness, không phải classification hợp lệ. Một field không
được có hai owner.

### Không đồng nhất policy với compliance system

`config/policy.yaml` chỉ là desired state cho một số cấu hình ERPNext. Nó không
phải là toàn bộ hồ sơ tuân thủ kế toán/thuế của doanh nghiệp và không được dùng
để kết luận hệ thống đã tuân thủ pháp luật.

| Phạm vi | Owner | Không thuộc policy vì |
|---|---|---|
| Company bootstrap và các setting ERPNext được chọn | `config/policy.yaml` | Đây là cấu hình desired state của ERPNext |
| Default/runtime Docker, database, Redis, backup, endpoint | `config/config.yaml` | Đây là system operation, không phải business policy |
| Customer, Supplier, Item, Account, Warehouse, Address | Business API/ERPNext DB | Đây là master/entity có lifecycle, policy chỉ tham chiếu |
| Invoice, Order, Receipt, Payment, Journal Entry, Stock movement | Business API/ERPNext DB | Đây là transaction phát sinh, không phải baseline config |
| GL Entry, Stock Ledger Entry, Payment Ledger, totals/calculated fields | ERPNext runtime | Đây là derived state, không được nhập vào policy |
| Hóa đơn điện tử, ký số, cấp mã, gửi cơ quan thuế, thay thế/điều chỉnh | Nhà cung cấp e-invoice + Headless BE integration | Đây là dịch vụ và integration lifecycle bên ngoài ERPNext policy |
| Tax/legal interpretation, VAT matrix, accounting regime, account mapping | Kế toán trưởng/tài liệu nghiệp vụ | Đây là quyết định pháp lý/nghiệp vụ, không tự suy ra từ ERPNext field |
| Secret, API key, certificate, provider credential | Secret store/.env | Không được lưu trong policy hoặc fallback |
| Backup retention, restore evidence, legal hold | Operations/compliance storage | Đây là control vận hành và bằng chứng lưu trữ |

`config/policy-full.yaml` chỉ là technical fallback/reference cho các DocType đã
được khai báo trong `policy.yaml`. Nó không mở rộng ownership, không được apply
trực tiếp và không phải legal policy. Giá trị explicit trong policy chính thắng;
`0`, `null`, `''`, `{}` và `[]` không được coi là thiếu.

### Boundary migration đã hoàn tất

- Country/currency có một owner duy nhất là `config/policy.yaml`; launcher lấy
  hai giá trị từ `policy.bootstrap.company`. `Global Defaults` không còn là
  mirror bắt buộc trong operational policy.
- Settings ngoài product scope và `User`/`User Permission` không còn được
  policy nhận ownership. User, credential, role assignment và User Permission
  theo cá nhân thuộc Identity API/DB.
- Boundary migration đã được kiểm tra trong registry-driven acceptance. Không
  còn migration gap là blocker của Phase 8.
- `config/policy.yaml` là production baseline gồm 28 document thật; registry
  `contracts/scope.yml` rộng hơn và quản lý 56 managed/conditional source
  bằng disposable fixture, không materialize acceptance fixture vào production.

## 3. Baseline đang được quản lý

`config/policy.yaml` hiện có 28 document native:

| Nhóm | Native document | Classification | Trạng thái |
|---|---|---|---|
| Accounts | Accounting Period `FY 2026 - LTVN` | `managed` | Policy period configured through 2026-08-14 |
| Settings | Accounts Settings | `managed` | Round-trip baseline pass |
| Settings | Buying Settings | `managed` | Round-trip baseline pass |
| Settings | Currency Exchange Settings | `managed` | Round-trip baseline pass; credential bị loại |
| Settings | Delivery Settings | `managed` | Round-trip baseline pass |
| Settings | Item Variant Settings | `managed` | Round-trip baseline pass |
| Settings | Ledger Health Monitor | `managed` | Round-trip baseline pass |
| Settings | Pegged Currencies | `managed` | Round-trip baseline pass |
| Settings | POS Settings | `managed` | Legacy baseline; phải phân loại lại vì POS ngoài scope |
| Settings | Selling Settings | `managed` | Round-trip baseline pass |
| Settings | Stock Reposting Settings | `managed` | Round-trip baseline pass |
| Settings | Stock Settings | `managed` | Round-trip baseline pass |
| Tax | Sales Taxes and Charges Template `Vietnam Tax - LTVN` | `managed` | Native rate 10 readback pass |
| Tax | Purchase Taxes and Charges Template `Vietnam Tax - LTVN` | `managed` | Native rate 10 readback pass |
| Tax | Item Tax Template `Vietnam Tax - LTVN` | `managed` | Native rate 10 readback pass |

Thuế không nằm trong `Accounts Settings`. ERPNext bootstrap đọc
[`country_wise_tax.json`](../apps/erpnext/erpnext/setup/setup_wizard/data/country_wise_tax.json),
tạo Account `VAT` và ba template native. Policy phải giữ `rate`, `account_head`,
child rows và link native; không tạo record shadow.

## 4. Persistent Settings trong phạm vi

| Module | DocType | Classification | Implementation |
|---|---|---|---|
| Accounts | [Accounts Settings](../apps/erpnext/erpnext/accounts/doctype/accounts_settings/accounts_settings.json) | `managed` | Baseline pass |
| Accounts | [Currency Exchange Settings](../apps/erpnext/erpnext/accounts/doctype/currency_exchange_settings/currency_exchange_settings.json) | `conditional` | Non-secret fields baseline; `access_key` là `secret` |
| Accounts | [Ledger Health Monitor](../apps/erpnext/erpnext/accounts/doctype/ledger_health_monitor/ledger_health_monitor.json) | `managed` | Baseline pass |
| Accounts | [Pegged Currencies](../apps/erpnext/erpnext/accounts/doctype/pegged_currencies/pegged_currencies.json) | `conditional` | Baseline serialization pass |
| Buying | [Buying Settings](../apps/erpnext/erpnext/buying/doctype/buying_settings/buying_settings.json) | `managed` | Baseline pass |
| Selling | [Selling Settings](../apps/erpnext/erpnext/selling/doctype/selling_settings/selling_settings.json) | `managed` | Baseline pass |
| Stock | [Delivery Settings](../apps/erpnext/erpnext/stock/doctype/delivery_settings/delivery_settings.json) | `managed` | Baseline pass |
| Stock | [Item Variant Settings](../apps/erpnext/erpnext/stock/doctype/item_variant_settings/item_variant_settings.json) | `managed` | Baseline pass |
| Stock | [Stock Reposting Settings](../apps/erpnext/erpnext/stock/doctype/stock_reposting_settings/stock_reposting_settings.json) | `managed` | Baseline pass |
| Stock | [Stock Settings](../apps/erpnext/erpnext/stock/doctype/stock_settings/stock_settings.json) | `managed` | Baseline pass |
| Cross-cutting | [Global Defaults](../apps/erpnext/erpnext/setup/doctype/global_defaults/global_defaults.json) | `excluded` | Derived from `policy.bootstrap.company`; not duplicated in operational policy |

`System Settings` fields thuộc language/timezone/format/security runtime do
`config.yaml` quản lý, không được lặp trong policy.

## 5. Non-Single policy đã nghiệm thu

### 5.1. Accounts, tax và commercial

| Native DocType | Classification | Implementation |
|---|---|---|
| Cost Center | `managed` | Cost Center root và ledger dùng bởi VAT/Tax Template |
| Accounting Dimension / Accounting Dimension Filter | `conditional` | Native dependency, structural và round-trip pass |
| Accounting Period | `managed` | Native acceptance exists; tenant period policy values pending accounting approval |
| Bank Transaction Rule | `conditional` | Policy definition pass; business transaction API vẫn thuộc Phase 9 |
| Cheque Print Template | `conditional` | Native round-trip pass |
| Cost Center Allocation | `conditional` | Child order và native round-trip pass |
| Dunning Type | `conditional` | Native round-trip pass |
| Financial Report Template | `conditional` | Native round-trip pass |
| Journal Entry Template | `conditional` | Native round-trip pass |
| Loyalty Program | `conditional` | Native round-trip pass |
| Payment Term / Payment Terms Template | `conditional` | Schedule controller effect pass |
| Pricing Rule / Promotional Scheme | `conditional` | Native pricing 5% controller effect pass |
| Sales/Purchase/Item Tax Template | `managed` | Native controller acceptance exists; tenant tax matrix values pending accounting approval |
| Shipping Rule | `conditional` | Native shipping charge effect pass |
| Tax Category / Tax Rule | `managed` | Native selection acceptance exists; tenant tax matrix values pending accounting approval |
| Tax Withholding Category / Group | `conditional` | Native round-trip pass |
| Terms and Conditions | `conditional` | Native round-trip pass |

`Budget`, `POS Profile` và `Subscription Plan` ngoài product scope hiện tại,
không được tính là policy gap của Phase 8.

### 5.2. Buying và Stock

| Native DocType | Classification | Implementation |
|---|---|---|
| Supplier Scorecard và criteria/standing/variable | `conditional` | Criteria/weight controller effect pass |
| Inventory Dimension | `conditional` | Native schema và round-trip pass |
| Putaway Rule | `conditional` | Native dependency và round-trip pass |
| Quality Inspection Template | `conditional` | Reading propagation effect pass |
| Shipment Parcel Template | `conditional` | Native round-trip pass |
| Stock Entry Type | `conditional` | Native purpose effect pass |

Các template chỉ được materialize khi capability tương ứng được bật. Empty
module state không được biến thành hàng loạt document rỗng trong YAML.

## 6. Policy Frappe dùng chung

| Native source | Classification | Boundary/implementation |
|---|---|---|
| Custom Role, Role Profile | `conditional` | Definition dùng cho module public thuộc policy; standard role không export |
| Workflow State, Workflow Action Master, Workflow | `conditional` | Typed round-trip và native transition pass |
| Custom DocPerm | `conditional` | Permission matrix bằng hai user thật pass |
| User, Employee, API key, user-role assignment | `entity`/`secret` | Identity API/DB; không thuộc policy |
| User Permission theo cá nhân | `entity` | Identity API/DB; không thuộc policy |
| Assignment Rule | `conditional` | Policy khi áp dụng resource public |
| Document Naming Rule | `conditional` | Policy; counter `tabSeries` không export |
| Print Settings, Print Format, Letter Head | `conditional` | Policy khi dùng resource public |
| Email Template, Notification | `conditional` | Policy; endpoint/credential ở config/secret store |
| Property Setter | `excluded` | Chỉ fixture/migration đã review trong source |
| Custom Field, Client Script, Server Script | `excluded` | Executable/schema customization phải deploy bằng app |

## 7. Entity và transient state

Các loại sau không thuộc `policy.yaml`:

- Company sau bootstrap, Account, Warehouse, Bank, Bank Account,
  Mode of Payment, Customer, Supplier, Item, Address và Contact: `entity`;
- quotation, order, invoice, receipt, Journal Entry, Payment Request và stock
  movement: `entity` transaction;
- GL Entry, Payment Ledger Entry, Stock Ledger Entry, Bin, queue/outbox, cache,
  naming counter: derived runtime state;
- Các Desk tool trong bảng dưới đây là `transient` input/result theo phiên:

| Module | Native tool |
|---|---|
| Accounts | [Bank Clearance](../apps/erpnext/erpnext/accounts/doctype/bank_clearance/bank_clearance.json) |
| Accounts | [Bank Reconciliation Tool](../apps/erpnext/erpnext/accounts/doctype/bank_reconciliation_tool/bank_reconciliation_tool.json) |
| Accounts | [Bisect Accounting Statements](../apps/erpnext/erpnext/accounts/doctype/bisect_accounting_statements/bisect_accounting_statements.json) |
| Accounts | [Chart of Accounts Importer](../apps/erpnext/erpnext/accounts/doctype/chart_of_accounts_importer/chart_of_accounts_importer.json) |
| Accounts | [Opening Invoice Creation Tool](../apps/erpnext/erpnext/accounts/doctype/opening_invoice_creation_tool/opening_invoice_creation_tool.json) |
| Accounts | [Payment Reconciliation](../apps/erpnext/erpnext/accounts/doctype/payment_reconciliation/payment_reconciliation.json) |
| Selling | [SMS Center](../apps/erpnext/erpnext/selling/doctype/sms_center/sms_center.json) |
| Stock | [Quick Stock Balance](../apps/erpnext/erpnext/stock/doctype/quick_stock_balance/quick_stock_balance.json) |
| Cross-cutting | [Authorization Control](../apps/erpnext/erpnext/setup/doctype/authorization_control/authorization_control.json) |

Ngoại lệ duy nhất là identity tối thiểu của Company trong `bootstrap` của
`policy.yaml`. Controller native tạo Company/Chart of Accounts/country fixture;
policy không nhận ownership lifecycle của các entity được sinh ra.

## 8. Gate hoàn thành Phase 8

Phase 8 chỉ `COMPLETE` khi:

1. Country/currency có một owner; runtime allowlist không nhận ownership
   User/User Permission hoặc module ngoài product scope. Gate này đã pass.
2. Mọi source trong các mục 4–6 có classification và `unknown = 0`.
3. Mọi `managed` và `conditional-enabled` giữ đúng native type, child row,
   Unicode, `true`, `false`, `0`, `null` và empty value.
4. Dependency tới Account/Cost Center/Warehouse được kiểm tra nhưng không làm
   policy sở hữu entity.
5. Export→apply→export canonical-equal; apply lần hai trả zero change.
6. Invalid link/field/dependency và injected controller failure rollback cả
   YAML lẫn DB.
7. Secret không xuất hiện trong YAML, diff, log hoặc generated artifact.
8. Upgrade gate fail khi source/field trong phạm vi chưa phân loại xuất hiện.
9. Windows/Docker checkout chạy launcher không flag, zero drift và toàn bộ
   acceptance test node pass riêng lẻ; full-suite run là tùy chọn. Ubuntu không
   thuộc tiêu chí nghiệm thu Phase 8.

Gate trên đã pass ngày 2026-08-12: scanner đọc 811 DocType/13.624 field với
`unknown=0`, `unclassified=0`, `schema_drift=0` và
`managed_entries_without_acceptance=0`; 56 source được kiểm tra theo shard dưới
70 giây cho test nhỏ và 5 phút cho test gộp. Tax 0/5/8/10, commercial, Stock/Buying, workflow/permission,
naming/render/notification và failure injection tại asset/document/delete/cache/
commit đều pass. Runtime drift, round-trip diff, leakage và residue cuối bằng 0.

## 9. Lệnh kiểm tra

Checklist câu hỏi nghiệp vụ để hoàn thiện các giá trị trong policy nằm tại
[`Policy Configuration Questionnaire`](Policy_Configuration_Questionnaire.md).
Tài liệu này là nơi ghi câu trả lời, người xác nhận và trạng thái quyết định;
inventory chỉ giữ ownership và evidence kỹ thuật.

Production chỉ chạy launcher không flag. Các action dưới đây dành cho
acceptance/chẩn đoán:

```powershell
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action policy-export
.\docker-start.ps1 -Action policy-plan
.\docker-start.ps1 -Action policy-apply
.\docker-start.ps1 -Action verify
uv run pytest tests/test_policy.py -q
uv run pytest tests/integration/test_policy_runtime.py -m integration -q
```

Các lệnh trên chỉ chứng minh phần đã khai báo đồng bộ với runtime. Completeness
được quyết định bởi inventory trong tài liệu này và các gate ở mục 8.
