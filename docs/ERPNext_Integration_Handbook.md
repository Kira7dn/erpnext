# ERPNext Integration Handbook

Tài liệu này mô tả cách frontend và ứng dụng tích hợp gọi trực tiếp Frappe API
trong site ERPNext. ERPNext là source of truth cho schema, permission,
validation, controller và lifecycle; không gọi database trực tiếp.

## Trạng thái runtime

## Tiến độ contract

Cập nhật 2026-08-11: Phase 4 giữ nguyên trạng thái pass. Phase 5 đã mở curated
API lên 11 resource: Customer, Quotation, Sales Order, Delivery Note, Sales
Invoice, Purchase Invoice, Payment Entry, Supplier, Purchase Order, Item và
Warehouse. Docker core acceptance đã pass auth token, system APIs, upload,
Unicode/list controls, hai business flow, lifecycle và durable outbox.
Webhook/realtime acceptance đã pass với durable staging consumer chạy trong
Docker; credential local được sinh tạm và không ghi vào artifact.

## Phase 5 — API coverage và delivery

Phase 5 test có chọn lọc các API nghiệp vụ quan trọng. P0 gồm token auth,
`health`/`runtime_info`/`runtime_snapshot`, curated resource API, upload file và
chuỗi Quotation → Sales Order → Sales Invoice. P1 gồm pagination/filter/schema,
Unicode URL, validation/error envelope, concurrent idempotency và
read-after-timeout reconciliation.

Phase 5 không coi toàn bộ catalog DocType metadata là runtime scope. Webhook và
realtime chỉ được acceptance khi staging consumer cố định reachable và ký nhận,
retry, dedupe, reconnect đều pass.

Kiểm tra bằng Docker:

```text
site: frontend
apps: frappe, erpnext, letron_api
frontend: lấy từ `runtime.server_url` trong contract và `project.http_port` trong `config.yml`
health: GET /api/method/letron_api.api.health
```

Kiểm tra lại bất cứ lúc nào:

```powershell
.\docker-start.ps1 -Action verify
.\docker-start.ps1 -Action inspect
```

`verify` kiểm tra runtime snapshot và HTTP health. `inspect` lấy DocType
metadata, permission và danh sách app trực tiếp trong Frappe container.

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

`contracts/generated/catalog.json` là inventory đầy đủ của runtime: toàn bộ DocType và
whitelisted method được phát hiện, kể cả method chưa public trong contract.
`contracts/generated/openapi.yaml`/`.json` là contract curated: chỉ có allowlist,
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
file public cho Accounts, Buying, Selling và Stock.

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

Runtime cũng công bố submit/cancel cho Purchase Invoice, Sales Order và Purchase
Order. Các route này chuyển sang `letron_api.api.document_action`; quyền và
validation vẫn do Document controller native của Frappe thực hiện. Amend và
action suy đoán không được expose.

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

Upload size chịu giới hạn `frontend.upload_size` trong `config.yml`. File URL
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

Generated artifact bị Git ignore và không chứa credential. Frappe còn có thể
ghi cảnh báo tương thích DuckDB `cleanup_old_syncs`; cảnh báo này không làm
health API hoặc startup fail.
