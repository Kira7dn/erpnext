# ERPNext Integration Handbook

Tài liệu này mô tả cách frontend và ứng dụng tích hợp gọi trực tiếp Frappe API
trong site ERPNext. ERPNext là source of truth cho schema, validation,
controller và lifecycle. `config/config.yaml` và `config/policy.yaml` là hai SOT
được version-control trên compute; `letron_api` reconcile chúng vào runtime và
các DocType native. Không gọi database trực tiếp cho nghiệp vụ.

## Contract được hỗ trợ

Contract hiện hành có 5 module, 37 resource và 215 business operation; 215 đã
`passed`, 0 operation `not-tested` sau khi Phase 11 đạt COMPLETE.
Control plane cấu hình có 2 operation riêng và không được tính vào business
operation count. Team tích hợp chỉ sinh SDK từ
artifact committed trong `contracts/openapi/`, không từ runtime catalog.

Roadmap, tiến độ và evidence bàn giao chỉ có một SOT tại
[ERP PRD](ERP_PRD.md). Classification policy nằm tại
[Configuration Inventory](Configuration_Inventory.md). Handbook này chỉ mô tả
capability đã dùng được; nội dung `PLANNED` không được trình bày như API hiện có.

## Config và policy control

Lệnh triển khai production duy nhất trên Windows là `.\docker-start.ps1`
(Ubuntu: `./erpctl`). Không truyền action; launcher tự chạy validate, migrate,
bootstrap, sync và reload runtime. Các lệnh `-Action` trong tài liệu này chỉ là
test/chẩn đoán nội bộ.

`config/config.yaml` quản lý system/runtime. Target owner của Company bootstrap,
country, currency và business policy là `config/policy.yaml`. Production policy
hiện có 14 native document thật; conditional coverage không được materialize
vào production YAML mà dùng disposable acceptance fixture.

Country/currency không còn mirror trong `config.yaml`; launcher lấy bootstrap
input từ policy. Sau bootstrap, Company identity không được đổi qua PUT thông thường.
User, Employee, API key, user-role assignment và User Permission theo cá nhân
thuộc Identity API/DB, không thuộc policy.

`letron_api` không diễn giải lại nghiệp vụ. YAML giữ nguyên field và child row
native; wrapper chỉ export, validate, diff, apply bằng controller Frappe và đọc
lại để xác nhận. Password/API secret không nằm trong YAML: YAML chỉ giữ
`${ENV_NAME}`, giá trị thật nằm trong `.env` bị Git ignore. Metadata runtime và
business documents không được export.

```powershell
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action policy-export
.\docker-start.ps1 -Action bootstrap
.\docker-start.ps1 -Action config-plan
.\docker-start.ps1 -Action config-apply
.\docker-start.ps1 -Action policy-plan
.\docker-start.ps1 -Action policy-apply
.\docker-start.ps1 -Action verify
```

`policy-bootstrap`, `config-sync`, rồi `policy-sync` chạy sau migrate và phải
hoàn tất trước backend/workers. Bootstrap gọi controller Company native, dùng
Standard Chart of Accounts và country fixture của ERPNext; chạy lặp lại là
idempotent và từ chối site có nhiều Company hoặc Company khác YAML.
`policy-plan` phải báo `drift_count: 0`; apply lần hai phải báo `applied: 0`.
Hai kết quả này chỉ xác nhận phạm vi đã khai báo, không chứng minh full business-policy coverage.
Managed field sửa trực tiếp qua Desk/API sẽ bị từ chối. Health và runtime
snapshot chỉ công bố version/hash/drift, không công bố nội dung policy hoặc
secret. Policy không phải public resource nên curated contract vẫn giữ
23 resource và 137 operation.

System Manager có thể dùng control-plane API nội bộ để chỉnh đúng hai file trên
compute. GET trả YAML cùng `source_sha256`; PUT yêu cầu chính hash đó, validate
candidate, ghi atomic và mặc định apply/readback:

```text
GET /api/method/letron_api.config_control.get_configuration?kind=config|policy
PUT /api/method/letron_api.config_control.put_configuration
```

PUT body gồm `kind`, `content`, `expected_source_sha256`, `apply_now`. Chỉ hai
giá trị kind cố định được chấp nhận; nội dung tối đa 2 MiB. Secret đã resolve
không bao giờ được trả về. Với thay đổi system cần recreate container, response
trả `restart_required: true` và operator chạy lại `.\docker-start.ps1` hoặc
`./erpctl`, không truyền action.

PUT dùng compensated transaction: candidate phải qua validator liên file,
Company identity không được đổi, và hash cũ phải khớp. Conflict trả 409. Nếu
native apply/readback thất bại, wrapper phục hồi chính xác YAML cũ, apply lại
runtime cũ và fail-closed nếu rollback cũng thất bại. `apply_now=false` chỉ
được phép ở developer test site.

Ví dụ update có optimistic lock:

```json
{
  "kind": "policy",
  "content": "<toàn bộ policy.yaml UTF-8>",
  "expected_source_sha256": "<hash nhận từ GET>",
  "apply_now": true
}
```

Client phải GET lại khi nhận 409. Với 417, sửa YAML/invariant thay vì retry;
với 500 rollback failure, dừng write và gọi health/runtime snapshot.

## Accounts operational core

Các route đã công bố:

```text
/api/v1/accounts/banks
/api/v1/accounts/bank-accounts
/api/v1/accounts/modes-of-payment
/api/v1/accounts/cost-centers
/api/v1/accounts/journal-entries
/api/v1/accounts/payment-requests
```

Mỗi resource có list/create/detail/update/delete. Journal Entry và Payment
Request có thêm `POST /{name}/submit` và `POST /{name}/cancel`; action gọi
lifecycle native của document.

Journal Entry phải cân bằng debit/credit và chỉ tham chiếu Account thật. Cost
Center giữ tree do Frappe quản lý, xóa leaf trước parent. Payment Request
`Outward` tham chiếu Purchase Invoice đã submit. Bank Account và Mode
of Payment dùng Company/account mapping thật, không tạo authorization hoặc
ledger song song.

Account, GL Entry và Payment Ledger Entry vẫn là source-of-truth nội bộ và
không có public CRUD. Capability chưa xuất hiện trong committed OpenAPI không
được gọi qua generic fallback. Kế hoạch mở rộng nằm trong PRD, không thuộc
handbook contract hiện hành.

## Authentication và headers

Production dùng API token hoặc session do hệ thống xác thực cấp. Không ghi
token vào source, OpenAPI artifact hoặc log.

```http
Authorization: token <api-key>:<api-secret>
Content-Type: application/json
Accept: application/json
X-Request-Id: <unique-request-id>
X-Idempotency-Key: <unique-key-for-side-effect>
```

Health endpoint được phép guest để Docker health check. Các API resource và
method còn lại chịu permission của Frappe.

### Integration user và API key

Không dùng Administrator cho consumer. System Manager tạo User native, gán
đúng role tối thiểu rồi issue/rotate secret bằng method native:

```bash
curl -X POST http://localhost:8080/api/method/frappe.core.doctype.user.user.generate_keys \
  -H "Authorization: token $SYSTEM_MANAGER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user":"integration@example.com"}'
```

Response trả `api_secret` đúng một lần; lưu trong secret manager. Gọi lại
method sẽ rotate secret. Revoke bằng cách System Manager disable User native
(`PUT /api/resource/User/<email>` với `{"enabled":0}`); generic route này chỉ
là thao tác quản trị, không phải public business contract.

| Phạm vi | Role khởi điểm |
|---|---|
| Config/policy control | System Manager |
| Accounts draft/read | Accounts User |
| Accounts submit/cancel | Accounts Manager và quyền submit native |
| Selling | Sales User/Sales Manager theo action native |
| Buying | Purchase User/Purchase Manager theo action native |
| Stock | Stock User/Stock Manager theo action native |
| Contacts | Permission native; kiểm tra create riêng vì Employee có thể được phép |

User Permission theo Company tiếp tục do Frappe enforce. Acceptance phải chạy
lại sau mọi thay đổi role hoặc Custom DocPerm.

## Response và lỗi

Response thành công thường bọc dữ liệu trong `message` hoặc `data`:

```json
{"message": {"name": "CUST-0001", "customer_name": "Example"}}
```

Lỗi cần xử lý theo HTTP status và không được chỉ kiểm tra chuỗi message:

| Status | Ý nghĩa | Cách xử lý |
|---|---|---|
| 400 | Payload/filter không hợp lệ | Sửa request, không retry mù |
| 401 | Thiếu hoặc sai authentication | Refresh credential/session |
| 403 | Không có permission | Hiển thị lỗi phân quyền |
| 404 | Không tồn tại resource/method | Kiểm tra name và API catalog |
| 409 | Conflict/duplicate | Đọc lại resource theo idempotency key |
| 417 | Validation native của Frappe | Sửa payload/config, không retry |
| 429 | Rate limit | Retry exponential backoff |
| 5xx | Lỗi server tạm thời | Retry có giới hạn rồi đưa vào reconciliation |

## Public Resource API

Các contract module dùng public alias dạng resource chuẩn. Ví dụ Sales Invoice:

```text
POST /api/v1/accounts/sales-invoices
GET  /api/v1/accounts/sales-invoices/{name}
PUT  /api/v1/accounts/sales-invoices/{name}
DELETE /api/v1/accounts/sales-invoices/{name}
```

Alias này được app `letron_api` rewrite vào Document API native của Frappe; không
được tự gọi child DocType như một resource độc lập.

| Module | Public resource |
|---|---|
| Accounts | Sales Invoice, Purchase Invoice, Payment Entry, Bank, Bank Account, Mode of Payment, Cost Center, Journal Entry, Payment Request |
| Buying | Supplier, Purchase Order |
| Contacts | Address, Contact |
| Selling | Customer, Quotation, Sales Order, Delivery Note |
| Stock | Item, Warehouse, Material Request, Purchase Receipt, Stock Entry, Item Price, Stock Reconciliation, Serial No, Batch, Quality Inspection, Pick List, Shipment, Landed Cost Voucher, Stock Reservation Entry |

`Dynamic Link` chỉ xuất hiện trong `Address.links` và `Contact.links`; không có
CRUD riêng. Stock Reconciliation, Serial No, Batch, Bin và Stock Ledger Entry
không thuộc contract hiện hành.

Các chuỗi tích hợp chính:

- Customer/Supplier → Address/Contact qua child `links`.
- Material Request → Purchase Order → Purchase Receipt; Purchase Receipt tham
  chiếu Purchase Order đã submit.
- Stock Entry dùng stock item và warehouse thật cho receipt, issue hoặc transfer;
  không ghi trực tiếp Stock Ledger Entry.
- Item → Item Price theo Price List, UOM, currency và `price_list_rate`.

### List

```bash
curl -G http://localhost:8080/api/v1/selling/customers \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "X-Request-Id: req-customer-list" \
  --data-urlencode 'fields=["name","customer_name"]' \
  --data-urlencode 'filters=[["Customer","disabled","=",0]]' \
  --data-urlencode 'order_by=modified desc' \
  --data-urlencode 'limit_page_length=20' \
  --data-urlencode 'limit_start=0'
```

Query parameters chính: `fields`, `filters`, `order_by`,
`limit_page_length`, `limit_start`. Frappe vẫn là nơi kiểm tra field và
permission.

### Get detail

```bash
curl http://localhost:8080/api/v1/selling/customers/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "X-Request-Id: req-customer-detail"
```

### Create, update, delete

```bash
curl -X POST http://localhost:8080/api/v1/selling/customers \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-customer-create" \
  -H "X-Idempotency-Key: customer-import-0001" \
  -d '{"customer_name":"Example","customer_group":"All Customer Groups","territory":"All Territories"}'

curl -X PUT http://localhost:8080/api/v1/selling/customers/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"Example Updated"}'

curl -X DELETE http://localhost:8080/api/v1/selling/customers/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN"
```

Không tự tạo tên, child row hoặc trạng thái nghiệp vụ ở FE nếu ERPNext có
controller đảm nhiệm việc đó.

## Catalog và OpenAPI curated

`contracts/generated/catalog.json` là catalog metadata runtime: toàn bộ DocType
và whitelisted method được phát hiện, kể cả method chưa public trong contract.
`contracts/generated/openapi.yaml`/`.json` là bản tái sinh để kiểm tra. Artifact
bàn giao bền vững nằm tại `contracts/openapi/public.yaml`/`.json`; control plane
nằm tại `contracts/openapi/control-plane.yaml`/`.json`, và manifest giữ checksum.
Public contract chỉ có allowlist,
các system method cụ thể và upload. Contract chỉ khai báo các
parent DocType trong `public_resources`; child DocType chỉ là schema dependency,
không có CRUD endpoint độc lập.

Catalog và OpenAPI đều có index theo `DocType.module` (Accounts, Stock,
Buying, Selling, CRM, Manufacturing...). `typed_modules` quyết định module
nào được phân tích chi tiết cho catalog; `public_resources` trong contract mới
quyết định resource nào được xuất thành API curated. Vì vậy Core, Desk, Setup,
Custom và các DocType khác không tự động thành public API chỉ vì thuộc một
module được phân tích.
Public typed route dùng `/api/v1/<module>/<resource>` và được rewrite về
Document API native.

Ngoài artifact tổng hợp, generator tạo OpenAPI riêng tại
`contracts/generated/openapi/modules/<module>.yaml` và `.json`; danh sách file nằm ở
`contracts/generated/openapi/index.json`. Mỗi module file public chỉ chứa resource
trong allowlist của module đó và các child-table dependency cần để schema hợp lệ.
Module technical catalog-only không có file public riêng. Contract hiện tạo các
file public cho Accounts, Buying, Contacts, Selling và Stock.

Mỗi OpenAPI operation có `x-test-status`: `passed`, `partial`, `not-tested` hoặc
`blocked`. Operation đã chạy trên Docker còn có `x-test-level` và
`x-test-evidence`; tổng hợp nằm tại `x-acceptance-summary`. Nguồn khai báo là
section `acceptance` trong contract, không sửa trực tiếp artifact generated.

Các lifecycle action được khai báo riêng trong `runtime.document_actions`,
không suy đoán từ tên DocType. Ví dụ Sales Invoice có:

```http
POST /api/v1/accounts/sales-invoices/{name}/submit
POST /api/v1/accounts/sales-invoices/{name}/cancel
```

Runtime cũng công bố submit/cancel cho Purchase Invoice, Sales Order, Purchase
Order, Material Request, Purchase Receipt, Stock Entry, Journal Entry và
Payment Request. Các route này chuyển
sang `letron_api.api.document_action`; quyền, validation và ledger vẫn do
Document controller native của Frappe thực hiện. Amend và action suy đoán không
được expose.

Chỉ các RPC được khai báo rõ trong `runtime.include_methods` mới xuất hiện trong
OpenAPI; không có RPC fallback theo tên method tùy ý.

## Webhook và realtime delivery

Mỗi create/update/submit/cancel của public resource ghi một
`Letron Event Outbox` trong cùng transaction. Worker chỉ gửi sau commit; scheduler
replay các row Pending/Blocked để không mất event sau restart. Payload có
`event_id`, `request_id`, `event_type`, `doctype`, `document_name`,
`occurred_at`, snapshot và REST reference.

Webhook ký HMAC SHA-256 trên đúng raw UTF-8 body qua header
`X-Letron-Signature: sha256=<hex>`. Mỗi channel có tối đa ba attempt; chỉ timeout
và 5xx được retry, 400/401/403/404 fail vĩnh viễn, mọi 2xx là acknowledgement.
Realtime phát native event `letron_resource_event` qua Frappe Socket.IO. Với
HTTP relay URL, adapter đồng thời POST bằng Bearer token; với `ws://`/`wss://`,
URL/token thuộc staging client dùng để kiểm tra connect/reconnect. Consumer phải
deduplicate theo event ID. REST luôn là source of truth.

Runbook khi consumer gián đoạn:

1. Kiểm tra HMAC trên raw body trước khi parse JSON.
2. Dedupe bằng `event_id`; chỉ trả 2xx sau khi event đã được lưu bền.
3. Khôi phục endpoint rồi để scheduler replay Pending/Blocked; không sửa outbox
   trực tiếp.
4. Với event Failed hoặc khoảng thời gian nghi mất notification, pull REST theo
   `modified`/business key và reconcile vì REST là SOT.
5. Rotate webhook/token trong `.env`, recreate worker/scheduler và kiểm tra một
   event canary; không ghi secret vào YAML, log hoặc evidence.

Config chỉ qua environment, không commit URL/credential:

```text
LETRON_WEBHOOK_URL
LETRON_WEBHOOK_SECRET
LETRON_WEBHOOK_TIMEOUT_MS
LETRON_REALTIME_URL
LETRON_REALTIME_TOKEN
```

## Whitelisted method API

Method giữ HTTP method khai báo trong `frappe.whitelist`; nếu decorator không
khai báo thì OpenAPI phản ánh GET và POST. Argument truyền trong JSON body:

```bash
curl -X POST http://localhost:8080/api/method/letron_api.api.health \
  -H "X-Request-Id: req-health" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Catalog đầy đủ method và source file tại `contracts/generated/catalog.json`. OpenAPI
được sinh tại `contracts/generated/openapi.yaml` và `contracts/generated/openapi.json`.

## DocType metadata và permission

```bash
curl -G http://localhost:8080/api/method/frappe.desk.form.load.getdoctype \
  -H "Authorization: token $FRAPPE_TOKEN" \
  --data-urlencode 'doctype=Customer'
```

Runtime snapshot dùng để kiểm tra nội bộ:

```powershell
.\docker-start.ps1 -Action inspect
```

## File upload

```bash
curl -X POST http://localhost:8080/api/method/upload_file \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -F "file=@./document.pdf" \
  -F "is_private=1" \
  -F "doctype=Customer" \
  -F "docname=CUST-0001"
```

Upload size chịu giới hạn `frontend.upload_size` trong `config/config.yaml`. File URL
trả về phải được lưu theo response Frappe, không tự suy diễn đường dẫn storage.

## Python và TypeScript

```python
import requests

response = requests.get(
    "http://localhost:8080/api/v1/selling/customers/CUST-0001",
    headers={"Authorization": f"token {api_key}:{api_secret}", "X-Request-Id": request_id},
    timeout=30,
)
response.raise_for_status()
customer = response.json()["data"]
```

```ts
const response = await fetch(`${baseUrl}/api/v1/selling/customers/CUST-0001`, {
  headers: {
    Authorization: `token ${apiKey}:${apiSecret}`,
    "X-Request-Id": requestId,
  },
});
if (!response.ok) throw new Error(`ERPNext request failed: ${response.status}`);
const customer = await response.json();
```

## Retry, idempotency và reconciliation

- Không retry lỗi 400/401/403/404.
- Retry 429 và 5xx với exponential backoff, giới hạn số lần.
- Mỗi write có side effect phải giữ nguyên `X-Idempotency-Key` khi retry.
- Sau timeout không được kết luận write thất bại; đọc lại theo business key hoặc
  idempotency key.
- Webhook/realtime chỉ là notification. Consumer phải đọc lại record bằng REST.
- Pull reconciliation là cơ chế xác nhận cuối cùng.

Workspace đã có durable delivery adapter. Khi staging config thiếu hoặc endpoint
không reachable, gate phải báo `blocked external`; không được thay bằng mock để
đánh dấu pass. Realtime không bao giờ là source of truth.

## Sinh artifact và kiểm tra

```powershell
uv run python -m lib.api_generator validate
uv run python -m lib.api_generator inspect
uv run python -m lib.api_generator generate
uv run pytest
.\docker-start.ps1 -Action verify
```

Catalog/module artifact trong `contracts/generated/` bị Git ignore; artifact
bàn giao trong `contracts/openapi/` được version-control và không chứa
credential. Frappe còn có thể
ghi cảnh báo tương thích DuckDB `cleanup_old_syncs`; cảnh báo này không làm
health API hoặc startup fail. Phase 8 xác nhận không có `Scheduled Job Type`
tên này, nên đây là known upstream migrate/restore warning.

Phase 8 `COMPLETE` trên Windows/Docker ngày 2026-08-12: 56 source dùng
registry-driven disposable acceptance; tax 0/5/8/10, GL, commercial,
Stock/Buying, workflow/permission và cross-cutting effect đều pass. Native apply
lần hai zero-change, asset public/private và fault tại asset/document/delete/
cache/commit rollback byte-clean, runtime zero drift, restore drill pass và
residue cuối bằng 0. Production `config/policy.yaml` vẫn chỉ giữ 14 document thật
và không chứa acceptance fixture.

Phase 9 `COMPLETE` trên Windows/Docker ngày 2026-08-13: API typed mới cho
Bank Transaction / Payment Reconciliation / Payment Order, policy ownership đúng
định nghĩa, và toàn bộ node acceptance trong `tests/integration/test_policy_runtime.py`
đã pass với runtime zero-drift, residue zero và cleanup fail-closed.

Phase 10 `COMPLETE` trên Windows/Docker ngày 2026-08-13: thêm Phase 10 public
resources `Lead`, `Opportunity`, `Request for Quotation`, `Supplier Quotation` vào
public contract và router. `uv run pytest tests/integration/test_crm_preorder.py -q -m integration --maxfail=1`
đã pass 20 operation và đáp ứng điều kiện COMPLETE theo chính sách Phase 10.

Phase 11 đã hoàn tất: đã thêm 8 Stock traceability resources vào public
contract/router và acceptance CRUD/readback/delete; phase được đánh dấu `COMPLETE`.

## Điều kiện nghiệm thu Phase 9 — Accounts reconciliation

Phase 9 chỉ được bàn giao production-ready khi có đủ ba lớp output: implementation
API typed, OpenAPI generated/validated và Docker acceptance evidence trên cùng
revision. Phạm vi gồm Bank Transaction, Payment Reconciliation, Payment Order và
native actions/lifecycle liên quan. `Bank Transaction Rule` là definition có thể
do policy sở hữu; transaction, Payment Entry, Journal Entry và ledger là runtime
entity, không export vào `config/policy.yaml`.

Checklist bắt buộc:

- Native controller tạo/readback/cancel/reconcile đúng link Company, Bank
  Account, Account, Party, amount, date, status và child rows.
- Payment Order và reconciliation tạo đúng native allocation/Payment Entry/
  Journal Entry, cân bằng debit/credit, cập nhật outstanding và không ghi trực
  tiếp ledger derived.
- API có permission bằng user thật, invalid link/type/state, duplicate reference,
  idempotency, retry và rollback khi controller lỗi.
- OpenAPI validate/check pass; không dùng generic Frappe endpoint làm public
  business contract.
  - Fixture registry có builder/dependency/effect assertion/cleanup `finally`; mỗi
    test node dưới 70 giây, chạy trên stack `erpnext` hiện hữu. Full-suite run là
    tùy chọn và không phải điều kiện ký COMPLETE.
- Tất cả test node đã collect trong registry phải pass riêng lẻ; không được có
  timeout, partial, not-tested hoặc blocked.
- Runtime snapshot, schema/API diff, unmanaged record, ledger residue, outbox
  residue, acceptance residue và secret leakage đều bằng `0`.

Chỉ khi toàn bộ checklist và evidence trên pass mới đổi Phase 9 từ `PLANNED` sang
`COMPLETE` và cập nhật OpenAPI, PRD, README, Configuration Inventory cùng revision.
