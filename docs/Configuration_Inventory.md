# Inventory cấu hình nghiệp vụ ERPNext

Cập nhật: 2026-08-12  
Runtime được kiểm tra: ERPNext `16.31.1`, Frappe `16.30.0`

## 1. Kết luận và phạm vi

Tài liệu này là inventory nguồn cấu hình của tenant, không phải tuyên bố rằng
`config/policy.yaml` đã bao phủ toàn bộ ERPNext.

Trạng thái thực tế:

- `config/config.yaml` quản lý system/runtime và một tập field của native
  `System Settings`.
- `config/policy.yaml` hiện có 15 document: 12 persistent Settings và ba native
  `Vietnam Tax` template do Company bootstrap của ERPNext sinh cho Sales,
  Purchase và Item, đều có rate `10`.
- Các rule/template khác như payment terms, pricing, shipping, SLA và Workflow
  hoàn chỉnh chưa có trong YAML.
- Vì vậy bundle hiện tại là **settings và access baseline**, chưa phải full
  business-policy bundle.

Ranh giới sở hữu:

| Loại | Source of truth |
|---|---|
| System/runtime | `config/config.yaml` |
| Business settings/rule/template/workflow/permission | `config/policy.yaml` sau khi được khai báo và test |
| Entity/master/transaction/lifecycle | ERPNext API và MariaDB |
| Secret thật | `.env`, `site_config.json` hoặc native encrypted password storage |
| Executable customization | Source/fixture/migration trong app, không nhét code vào policy YAML |

## 2. “File trong ERPNext” và “giá trị của tenant” là hai thứ khác nhau

Mỗi DocType native thường có:

```text
apps/erpnext/erpnext/<module>/doctype/<slug>/<slug>.json
apps/erpnext/erpnext/<module>/doctype/<slug>/<slug>.py
apps/erpnext/erpnext/<module>/doctype/<slug>/<slug>.js
```

- `.json` định nghĩa schema, field, permission mặc định và child table.
- `.py` là controller/validation/lifecycle native.
- `.js` là hành vi Desk phía client.
- Các file này không chứa giá trị riêng của tenant như VAT 8% hay payment term
  30 ngày.

Giá trị tenant nằm trong MariaDB:

| Kiểu native | Nơi lưu runtime |
|---|---|
| Single DocType | `tabSingles`, theo bộ ba `doctype`, `field`, `value` |
| DocType thường | Bảng `tab<DocType>` |
| Child row | Bảng `tab<Child DocType>`, liên kết bằng `parent`, `parenttype`, `parentfield` |
| Password field | Encrypted password storage `__Auth`, không export vào YAML |
| Naming counter | `tabSeries`, là runtime state chứ không phải policy |
| Site/runtime config | `sites/common_site_config.json`, `sites/<site>/site_config.json` |

`config/policy.yaml` chỉ là bản source-controlled của những native document đã
được Letron lựa chọn quản lý. Document chưa được lựa chọn vẫn chỉ nằm trong DB.

## 3. Ví dụ đầy đủ: ERPNext lưu thuế ở đâu

Mức thuế không nằm trong `Accounts Settings`.

| Vai trò | Native DocType/bảng | Source schema |
|---|---|---|
| Header thuế bán | `Sales Taxes and Charges Template` | [`sales_taxes_and_charges_template.json`](../apps/erpnext/erpnext/accounts/doctype/sales_taxes_and_charges_template/sales_taxes_and_charges_template.json) |
| Dòng thuế bán | `Sales Taxes and Charges`; có `charge_type`, `account_head`, `rate` | [`sales_taxes_and_charges.json`](../apps/erpnext/erpnext/accounts/doctype/sales_taxes_and_charges/sales_taxes_and_charges.json) |
| Header thuế mua | `Purchase Taxes and Charges Template` | [`purchase_taxes_and_charges_template.json`](../apps/erpnext/erpnext/accounts/doctype/purchase_taxes_and_charges_template/purchase_taxes_and_charges_template.json) |
| Dòng thuế mua | `Purchase Taxes and Charges`; có `category`, `account_head`, `rate` | [`purchase_taxes_and_charges.json`](../apps/erpnext/erpnext/accounts/doctype/purchase_taxes_and_charges/purchase_taxes_and_charges.json) |
| Thuế theo Item | `Item Tax Template` và `Item Tax Template Detail.tax_rate` | [`item_tax_template.json`](../apps/erpnext/erpnext/accounts/doctype/item_tax_template/item_tax_template.json), [`item_tax_template_detail.json`](../apps/erpnext/erpnext/accounts/doctype/item_tax_template_detail/item_tax_template_detail.json) |
| Điều kiện chọn template | `Tax Rule`; theo company, party/item/group, địa chỉ, ngày và priority | [`tax_rule.json`](../apps/erpnext/erpnext/accounts/doctype/tax_rule/tax_rule.json) |
| Nhóm điều kiện thuế | `Tax Category` | [`tax_category.json`](../apps/erpnext/erpnext/accounts/doctype/tax_category/tax_category.json) |

ERPNext native Company bootstrap đọc
`setup/setup_wizard/data/country_wise_tax.json`; với Việt Nam nó tạo account
`VAT` cùng Sales/Purchase/Item Tax Template `Vietnam Tax` rate `10`. Ba template
này hiện đã được materialize vào `config/policy.yaml`. Tax Category và Tax Rule
vẫn chưa có record.

## 4. Toàn bộ ERPNext Single DocType

Source ERPNext v16.31.1 có 31 Single DocType. Inventory này được kiểm tra tự
động bởi `tests/test_policy.py` để upstream không thể thêm Single mới mà không
được phân loại.

### 4.1. Persistent configuration — 20 loại được hỗ trợ, 12 Single active đang có trong YAML

| Module | DocType | Source schema |
|---|---|---|
| Accounts | Accounts Settings | [`accounts_settings.json`](../apps/erpnext/erpnext/accounts/doctype/accounts_settings/accounts_settings.json) |
| Accounts | Currency Exchange Settings | [`currency_exchange_settings.json`](../apps/erpnext/erpnext/accounts/doctype/currency_exchange_settings/currency_exchange_settings.json) |
| Accounts | Ledger Health Monitor | [`ledger_health_monitor.json`](../apps/erpnext/erpnext/accounts/doctype/ledger_health_monitor/ledger_health_monitor.json) |
| Accounts | Pegged Currencies | [`pegged_currencies.json`](../apps/erpnext/erpnext/accounts/doctype/pegged_currencies/pegged_currencies.json) |
| Accounts | POS Settings | [`pos_settings.json`](../apps/erpnext/erpnext/accounts/doctype/pos_settings/pos_settings.json) |
| Accounts | Subscription Settings | [`subscription_settings.json`](../apps/erpnext/erpnext/accounts/doctype/subscription_settings/subscription_settings.json) |
| Buying | Buying Settings | [`buying_settings.json`](../apps/erpnext/erpnext/buying/doctype/buying_settings/buying_settings.json) |
| CRM | Appointment Booking Settings | [`appointment_booking_settings.json`](../apps/erpnext/erpnext/crm/doctype/appointment_booking_settings/appointment_booking_settings.json) |
| CRM | CRM Settings | [`crm_settings.json`](../apps/erpnext/erpnext/crm/doctype/crm_settings/crm_settings.json) |
| ERPNext Integrations | Plaid Settings | [`plaid_settings.json`](../apps/erpnext/erpnext/erpnext_integrations/doctype/plaid_settings/plaid_settings.json) |
| Manufacturing | Manufacturing Settings | [`manufacturing_settings.json`](../apps/erpnext/erpnext/manufacturing/doctype/manufacturing_settings/manufacturing_settings.json) |
| Projects | Projects Settings | [`projects_settings.json`](../apps/erpnext/erpnext/projects/doctype/projects_settings/projects_settings.json) |
| Selling | Selling Settings | [`selling_settings.json`](../apps/erpnext/erpnext/selling/doctype/selling_settings/selling_settings.json) |
| Setup | Global Defaults | [`global_defaults.json`](../apps/erpnext/erpnext/setup/doctype/global_defaults/global_defaults.json) |
| Stock | Delivery Settings | [`delivery_settings.json`](../apps/erpnext/erpnext/stock/doctype/delivery_settings/delivery_settings.json) |
| Stock | Item Variant Settings | [`item_variant_settings.json`](../apps/erpnext/erpnext/stock/doctype/item_variant_settings/item_variant_settings.json) |
| Stock | Stock Reposting Settings | [`stock_reposting_settings.json`](../apps/erpnext/erpnext/stock/doctype/stock_reposting_settings/stock_reposting_settings.json) |
| Stock | Stock Settings | [`stock_settings.json`](../apps/erpnext/erpnext/stock/doctype/stock_settings/stock_settings.json) |
| Support | Support Settings | [`support_settings.json`](../apps/erpnext/erpnext/support/doctype/support_settings/support_settings.json) |
| Utilities | Video Settings | [`video_settings.json`](../apps/erpnext/erpnext/utilities/doctype/video_settings/video_settings.json) |

Tám Settings của module chưa dùng (`Appointment Booking`, `CRM`, `Plaid`,
`Manufacturing`, `Projects`, `Subscription`, `Support`, `Video`) vẫn được
wrapper nhận diện nhưng không auto-export. `Plaid Settings.plaid_secret`, `Currency Exchange Settings.access_key` và
`Video Settings.api_key` bị loại khỏi exporter vì là credential.

### 4.2. Transient Desk tools — 11/11 được kiểm kê nhưng không thuộc policy

Các Single sau giữ input/result tạm cho một thao tác Desk. Export chúng sẽ biến
trạng thái phiên làm việc thành deployment policy.

| Module | DocType | Source schema |
|---|---|---|
| Accounts | Bank Clearance | [`bank_clearance.json`](../apps/erpnext/erpnext/accounts/doctype/bank_clearance/bank_clearance.json) |
| Accounts | Bank Reconciliation Tool | [`bank_reconciliation_tool.json`](../apps/erpnext/erpnext/accounts/doctype/bank_reconciliation_tool/bank_reconciliation_tool.json) |
| Accounts | Bisect Accounting Statements | [`bisect_accounting_statements.json`](../apps/erpnext/erpnext/accounts/doctype/bisect_accounting_statements/bisect_accounting_statements.json) |
| Accounts | Chart of Accounts Importer | [`chart_of_accounts_importer.json`](../apps/erpnext/erpnext/accounts/doctype/chart_of_accounts_importer/chart_of_accounts_importer.json) |
| Accounts | Opening Invoice Creation Tool | [`opening_invoice_creation_tool.json`](../apps/erpnext/erpnext/accounts/doctype/opening_invoice_creation_tool/opening_invoice_creation_tool.json) |
| Accounts | Payment Reconciliation | [`payment_reconciliation.json`](../apps/erpnext/erpnext/accounts/doctype/payment_reconciliation/payment_reconciliation.json) |
| Manufacturing | BOM Update Tool | [`bom_update_tool.json`](../apps/erpnext/erpnext/manufacturing/doctype/bom_update_tool/bom_update_tool.json) |
| Selling | SMS Center | [`sms_center.json`](../apps/erpnext/erpnext/selling/doctype/sms_center/sms_center.json) |
| Setup | Authorization Control | [`authorization_control.json`](../apps/erpnext/erpnext/setup/doctype/authorization_control/authorization_control.json) |
| Stock | Quick Stock Balance | [`quick_stock_balance.json`](../apps/erpnext/erpnext/stock/doctype/quick_stock_balance/quick_stock_balance.json) |
| Utilities | Rename Tool | [`rename_tool.json`](../apps/erpnext/erpnext/utilities/doctype/rename_tool/rename_tool.json) |

## 5. Non-Single business policy trong ERPNext

Đây là phần inventory mà bundle hiện tại còn thiếu. Tất cả DocType dưới đây đã
có schema/controller native; Letron không cần tạo policy engine mới.

### 5.1. Accounts, tax, payment và commercial rules

| DocType | Nội dung policy | Source schema | YAML hiện tại |
|---|---|---|---|
| Accounting Dimension | Khai báo dimension và default | [`accounting_dimension.json`](../apps/erpnext/erpnext/accounts/doctype/accounting_dimension/accounting_dimension.json) | Allowlisted, 0 record |
| Accounting Dimension Filter | Account/dimension applicability | [`accounting_dimension_filter.json`](../apps/erpnext/erpnext/accounts/doctype/accounting_dimension_filter/accounting_dimension_filter.json) | Chưa hỗ trợ |
| Accounting Period | Khoảng ngày khóa/mở transaction theo role | [`accounting_period.json`](../apps/erpnext/erpnext/accounts/doctype/accounting_period/accounting_period.json) | Chưa hỗ trợ |
| Bank Transaction Rule | Quy tắc match/gán bank transaction | [`bank_transaction_rule.json`](../apps/erpnext/erpnext/accounts/doctype/bank_transaction_rule/bank_transaction_rule.json) | Chưa hỗ trợ |
| Budget | Ngưỡng và hành động khi vượt ngân sách | [`budget.json`](../apps/erpnext/erpnext/accounts/doctype/budget/budget.json) | Chưa hỗ trợ |
| Cheque Print Template | Tọa độ và format cheque | [`cheque_print_template.json`](../apps/erpnext/erpnext/accounts/doctype/cheque_print_template/cheque_print_template.json) | Chưa hỗ trợ |
| Cost Center Allocation | Quy tắc phân bổ phần trăm giữa cost center | [`cost_center_allocation.json`](../apps/erpnext/erpnext/accounts/doctype/cost_center_allocation/cost_center_allocation.json) | Chưa hỗ trợ |
| Dunning Type | Mức phí/lãi và nội dung nhắc nợ | [`dunning_type.json`](../apps/erpnext/erpnext/accounts/doctype/dunning_type/dunning_type.json) | Chưa hỗ trợ |
| Financial Report Template | Cấu trúc dòng báo cáo | [`financial_report_template.json`](../apps/erpnext/erpnext/accounts/doctype/financial_report_template/financial_report_template.json) | Chưa hỗ trợ |
| Item Tax Template | Thuế theo item/account | [`item_tax_template.json`](../apps/erpnext/erpnext/accounts/doctype/item_tax_template/item_tax_template.json) | Native `Vietnam Tax` rate 10 đã quản lý |
| Journal Entry Template | Dòng tài khoản JE mẫu | [`journal_entry_template.json`](../apps/erpnext/erpnext/accounts/doctype/journal_entry_template/journal_entry_template.json) | Chưa hỗ trợ |
| Loyalty Program | Quy tắc tích/đổi điểm | [`loyalty_program.json`](../apps/erpnext/erpnext/accounts/doctype/loyalty_program/loyalty_program.json) | Chưa hỗ trợ |
| Monthly Distribution | Tỷ lệ phân bổ budget theo tháng | [`monthly_distribution.json`](../apps/erpnext/erpnext/accounts/doctype/monthly_distribution/monthly_distribution.json) | Chưa hỗ trợ |
| POS Profile | Hành vi POS theo user/company/payment | [`pos_profile.json`](../apps/erpnext/erpnext/accounts/doctype/pos_profile/pos_profile.json) | Chưa hỗ trợ |
| Payment Term | Công thức một điều khoản thanh toán | [`payment_term.json`](../apps/erpnext/erpnext/accounts/doctype/payment_term/payment_term.json) | Chưa hỗ trợ |
| Payment Terms Template | Lịch thanh toán, discount, mode | [`payment_terms_template.json`](../apps/erpnext/erpnext/accounts/doctype/payment_terms_template/payment_terms_template.json) | Chưa hỗ trợ |
| Pricing Rule | Rate/discount/free-item và điều kiện áp dụng | [`pricing_rule.json`](../apps/erpnext/erpnext/accounts/doctype/pricing_rule/pricing_rule.json) | Chưa hỗ trợ |
| Promotional Scheme | Các slab và đối tượng khuyến mãi | [`promotional_scheme.json`](../apps/erpnext/erpnext/accounts/doctype/promotional_scheme/promotional_scheme.json) | Chưa hỗ trợ |
| Purchase Taxes and Charges Template | Thuế/phí mua, rate và account | [`purchase_taxes_and_charges_template.json`](../apps/erpnext/erpnext/accounts/doctype/purchase_taxes_and_charges_template/purchase_taxes_and_charges_template.json) | Native `Vietnam Tax` rate 10 đã quản lý |
| Sales Taxes and Charges Template | Thuế/phí bán, rate và account | [`sales_taxes_and_charges_template.json`](../apps/erpnext/erpnext/accounts/doctype/sales_taxes_and_charges_template/sales_taxes_and_charges_template.json) | Native `Vietnam Tax` rate 10 đã quản lý |
| Shipping Rule | Cước theo amount/weight/country | [`shipping_rule.json`](../apps/erpnext/erpnext/accounts/doctype/shipping_rule/shipping_rule.json) | Chưa hỗ trợ |
| Subscription Plan | Giá và chu kỳ subscription | [`subscription_plan.json`](../apps/erpnext/erpnext/accounts/doctype/subscription_plan/subscription_plan.json) | Chưa hỗ trợ |
| Tax Category | Nhóm điều kiện thuế | [`tax_category.json`](../apps/erpnext/erpnext/accounts/doctype/tax_category/tax_category.json) | Chưa hỗ trợ |
| Tax Rule | Chọn template thuế theo điều kiện | [`tax_rule.json`](../apps/erpnext/erpnext/accounts/doctype/tax_rule/tax_rule.json) | Chưa hỗ trợ |
| Tax Withholding Category | Rate, threshold và account khấu trừ | [`tax_withholding_category.json`](../apps/erpnext/erpnext/accounts/doctype/tax_withholding_category/tax_withholding_category.json) | Chưa hỗ trợ |
| Tax Withholding Group | Nhóm khấu trừ | [`tax_withholding_group.json`](../apps/erpnext/erpnext/accounts/doctype/tax_withholding_group/tax_withholding_group.json) | Chưa hỗ trợ |
| Terms and Conditions | Điều khoản dùng lại trên chứng từ | [`terms_and_conditions.json`](../apps/erpnext/erpnext/setup/doctype/terms_and_conditions/terms_and_conditions.json) | Chưa hỗ trợ |

`Finance Book`, `Account`, `Bank`, `Bank Account`, `Mode of Payment` và
`Cost Center` là entity/reference structure, không tự động trở thành policy.
Chúng tiếp tục thuộc API/DB theo ranh giới đã chốt.

`Payment Gateway Account`, telephony endpoint và provider account là integration
configuration. Mapping không bí mật có thể được quản lý có điều kiện, nhưng
credential phải đi qua `config.yaml`/`.env`, không được export nguyên document.

### 5.2. Stock, quality, CRM, project và support rules/templates

| DocType | Nội dung policy | Source schema | YAML hiện tại |
|---|---|---|---|
| Contract Template | Mẫu hợp đồng và fulfilment terms | [`contract_template.json`](../apps/erpnext/erpnext/crm/doctype/contract_template/contract_template.json) | Chưa hỗ trợ |
| Project Template | Task blueprint | [`project_template.json`](../apps/erpnext/erpnext/projects/doctype/project_template/project_template.json) | Chưa hỗ trợ |
| Supplier Scorecard | Công thức, period và cảnh báo đánh giá supplier | [`supplier_scorecard.json`](../apps/erpnext/erpnext/buying/doctype/supplier_scorecard/supplier_scorecard.json) | Chưa hỗ trợ |
| Supplier Scorecard Criteria | Tiêu chí và trọng số đánh giá | [`supplier_scorecard_criteria.json`](../apps/erpnext/erpnext/buying/doctype/supplier_scorecard_criteria/supplier_scorecard_criteria.json) | Chưa hỗ trợ |
| Supplier Scorecard Standing | Ngưỡng standing và cảnh báo | [`supplier_scorecard_standing.json`](../apps/erpnext/erpnext/buying/doctype/supplier_scorecard_standing/supplier_scorecard_standing.json) | Chưa hỗ trợ |
| Supplier Scorecard Variable | Biến dùng trong score formula | [`supplier_scorecard_variable.json`](../apps/erpnext/erpnext/buying/doctype/supplier_scorecard_variable/supplier_scorecard_variable.json) | Chưa hỗ trợ |
| Quality Feedback Template | Bộ tiêu chí feedback | [`quality_feedback_template.json`](../apps/erpnext/erpnext/quality_management/doctype/quality_feedback_template/quality_feedback_template.json) | Chưa hỗ trợ |
| Inventory Dimension | Dimension bổ sung cho stock ledger | [`inventory_dimension.json`](../apps/erpnext/erpnext/stock/doctype/inventory_dimension/inventory_dimension.json) | Chưa hỗ trợ |
| Putaway Rule | Quy tắc chọn warehouse | [`putaway_rule.json`](../apps/erpnext/erpnext/stock/doctype/putaway_rule/putaway_rule.json) | Chưa hỗ trợ |
| Quality Inspection Template | Parameter/specification kiểm tra | [`quality_inspection_template.json`](../apps/erpnext/erpnext/stock/doctype/quality_inspection_template/quality_inspection_template.json) | Chưa hỗ trợ |
| Shipment Parcel Template | Kích thước/khối lượng parcel mẫu | [`shipment_parcel_template.json`](../apps/erpnext/erpnext/stock/doctype/shipment_parcel_template/shipment_parcel_template.json) | Chưa hỗ trợ |
| Stock Entry Type | Purpose/type cho stock movement | [`stock_entry_type.json`](../apps/erpnext/erpnext/stock/doctype/stock_entry_type/stock_entry_type.json) | Chưa hỗ trợ |
| Service Level Agreement | Lịch support, priority, response/resolution | [`service_level_agreement.json`](../apps/erpnext/erpnext/support/doctype/service_level_agreement/service_level_agreement.json) | Chưa hỗ trợ |
| Email Digest | Lịch và nội dung digest theo user/company | [`email_digest.json`](../apps/erpnext/erpnext/setup/doctype/email_digest/email_digest.json) | Chưa hỗ trợ |

Các loại trên chỉ nên đưa vào policy khi module tương ứng được dùng. Việc module
không nằm trong public API roadmap không làm mất tính chất policy native, nhưng
không cần ép tenant khai báo document rỗng.

`Quality Goal`, `Quality Procedure`, `Routing`, `BOM`, `Project Type` và các
master mô tả cách vận hành có thể được version hóa riêng, nhưng vẫn là entity
nghiệp vụ. Chúng không mặc nhiên thuộc `policy.yaml`; muốn quản lý qua Git phải
có quyết định sở hữu riêng thay vì blanket-export.

### 5.3. Regional và integration configuration

| DocType | Quyết định | Source schema | Nơi nên quản lý |
|---|---|---|---|
| South Africa VAT Settings | Account mapping VAT theo company | [`south_africa_vat_settings.json`](../apps/erpnext/erpnext/regional/doctype/south_africa_vat_settings/south_africa_vat_settings.json) | Policy nếu tenant dùng South Africa |
| UAE VAT Settings | Account mapping VAT theo company | [`uae_vat_settings.json`](../apps/erpnext/erpnext/regional/doctype/uae_vat_settings/uae_vat_settings.json) | Policy nếu tenant dùng UAE |
| Incoming Call Settings | Call handling schedule | [`incoming_call_settings.json`](../apps/erpnext/erpnext/telephony/doctype/incoming_call_settings/incoming_call_settings.json) | Policy cho schedule; secret ở `.env` |
| Voice Call Settings | Telephony provider behavior | [`voice_call_settings.json`](../apps/erpnext/erpnext/telephony/doctype/voice_call_settings/voice_call_settings.json) | `config.yaml`/`.env` nếu chứa endpoint hoặc credential |
| Plaid Settings | Enable/schedule và Plaid environment | [`plaid_settings.json`](../apps/erpnext/erpnext/erpnext_integrations/doctype/plaid_settings/plaid_settings.json) | Đã có non-secret field trong policy; secret bị loại |

## 6. Policy native thuộc Frappe framework

ERPNext chạy trên Frappe nên một phần policy không nằm dưới `apps/erpnext`.
Source của chúng có trong runtime image tại
`/home/frappe/frappe-bench/apps/frappe/frappe/`.

| DocType | Runtime source schema | YAML hiện tại |
|---|---|---|
| Role | `core/doctype/role/role.json` | Không export; vocabulary runtime native |
| Role Profile | `core/doctype/role_profile/role_profile.json` | Không export |
| Workflow State | `workflow/doctype/workflow_state/workflow_state.json` | Không export |
| Workflow Action Master | `workflow/doctype/workflow_action_master/workflow_action_master.json` | Không export |
| Workflow | `workflow/doctype/workflow/workflow.json` | Allowlisted, 0 record |
| Custom DocPerm | `core/doctype/custom_docperm/custom_docperm.json` | Allowlisted, 0 record |
| User Permission | `core/doctype/user_permission/user_permission.json` | Allowlisted, 0 record |
| Print Settings | `printing/doctype/print_settings/print_settings.json` | Chưa hỗ trợ |
| Print Format | `printing/doctype/print_format/print_format.json` | Chưa hỗ trợ |
| Letter Head | `printing/doctype/letter_head/letter_head.json` | Chưa hỗ trợ |
| Email Template | `email/doctype/email_template/email_template.json` | Chưa hỗ trợ |
| Notification | `email/doctype/notification/notification.json` | Chưa hỗ trợ |
| Assignment Rule | `automation/doctype/assignment_rule/assignment_rule.json` | Chưa hỗ trợ |
| Document Naming Rule | `core/doctype/document_naming_rule/document_naming_rule.json` | Chưa hỗ trợ |
| Property Setter | `custom/doctype/property_setter/property_setter.json` | Chưa hỗ trợ; chỉ nên allowlist record đã review |

`Custom Field`, `Client Script`, `Server Script` và executable customization có
thể thay đổi schema hoặc chạy code. Chúng phải được review/deploy bằng app
fixture hoặc migration; không blanket-export từ một database vào policy YAML.
Naming counter trong `tabSeries` cũng không export; chỉ naming definition/rule
mới là policy.

## 7. Những gì là entity hoặc transaction, không phải policy

Không đưa các nhóm sau vào `policy.yaml` chỉ vì chúng có ảnh hưởng nghiệp vụ:

- Entity/master: Company, Account, Cost Center, Warehouse, Bank, Bank Account,
  Mode of Payment, Currency, UOM, Price List, Territory, Customer/Supplier/Item
  Group, Customer, Supplier, Item, Contact, Address, Employee, Project.
- Transaction: quotation/order/invoice/receipt/delivery, Journal Entry, Payment
  Request/Entry, Stock Entry, reconciliation document.
- Derived ledger/runtime state: GL Entry, Payment Ledger Entry, Stock Ledger
  Entry, Bin, queue/outbox, naming counter, report cache.

Các loại này sống trong ERPNext DB và được thay đổi qua API/controller native.
Ngoại lệ duy nhất hiện tại là identity tối thiểu của Company nằm trong section
`bootstrap` của `policy.yaml`; controller native tạo Company cùng chart/country
fixture một lần, sau đó entity vẫn sống trong DB. Entity khác phải đi qua API
hoặc import có version riêng, không biến thành policy và không tạo hai đường ghi.

## 8. Khoảng trống cần đóng trước khi gọi “full business policy”

Một bundle chỉ được gọi là full business policy khi:

1. Các DocType rule/template trong mục 5 và Frappe policy trong mục 6 đã được
   quyết định `managed`, `conditional` hoặc `excluded` bằng danh sách kiểm kê.
2. Export giữ nguyên field và child row native, bao gồm các field giá trị như
   tax `rate`, account link, priority, effective dates và conditions.
3. Dependency order xử lý entity link có sẵn trước rule/template nhưng không
   nhận quyền sở hữu các entity đó.
4. Secret detection bao phủ cả field `Password` và credential lưu sai kiểu
   `Data`; không ghi giá trị thật vào YAML.
5. Acceptance tạo ít nhất một policy có giá trị cụ thể, sửa YAML, apply, đọc lại
   native document, kiểm tra controller effect, tạo drift và recover.
6. Test completeness fail nếu upstream thêm Settings/rule/template quan trọng
   mà inventory chưa phân loại.

Cho tới khi sáu điều kiện này pass, tài liệu và health chỉ được nói
“settings/access baseline in-sync”, không được nói “100% business policy”.

## 9. Lệnh kiểm tra hiện tại

Triển khai production chỉ chạy `.\docker-start.ps1` không có flag. Các action
dưới đây là acceptance/chẩn đoán nội bộ:

```powershell
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action policy-export
.\docker-start.ps1 -Action policy-plan
.\docker-start.ps1 -Action policy-apply
.\docker-start.ps1 -Action verify
uv run pytest tests/test_policy.py -q
uv run pytest tests/integration/test_policy_runtime.py -m integration -q
```

Các lệnh trên chứng minh bundle đã khai báo đồng bộ với runtime; chúng không tự
chứng minh inventory business policy đã đầy đủ. Completeness phải được đối chiếu
với tài liệu này và các test coverage tương ứng.
