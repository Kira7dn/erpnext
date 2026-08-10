# ERPNext Integration Handbook

Tài liệu này mô tả cách frontend và ứng dụng tích hợp gọi trực tiếp Frappe API
trong site ERPNext. ERPNext là source of truth cho schema, permission,
validation, controller và lifecycle; không gọi database trực tiếp.

## Trạng thái runtime

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

## Generic Resource API

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
curl -G http://localhost:8080/api/resource/Customer \
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
curl http://localhost:8080/api/resource/Customer/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "X-Request-Id: req-customer-detail"
```

### Create, update, delete

```bash
curl -X POST http://localhost:8080/api/resource/Customer \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: req-customer-create" \
  -H "X-Idempotency-Key: customer-import-0001" \
  -d '{"customer_name":"Example","customer_group":"All Customer Groups","territory":"All Territories"}'

curl -X PUT http://localhost:8080/api/resource/Customer/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customer_name":"Example Updated"}'

curl -X DELETE http://localhost:8080/api/resource/Customer/CUST-0001 \
  -H "Authorization: token $FRAPPE_TOKEN"
```

Không tự tạo tên, child row hoặc trạng thái nghiệp vụ ở FE nếu ERPNext có
controller đảm nhiệm việc đó.

## Catalog và OpenAPI curated

`contracts/generated/catalog.json` là inventory đầy đủ của runtime: toàn bộ DocType và
whitelisted method được phát hiện, kể cả method chưa public trong contract.
`contracts/generated/openapi.yaml`/`.json` là contract curated: chỉ có allowlist,
generic resource/RPC fallback, metadata và upload. Contract khai báo typed
parent DocType theo các module runtime; child DocType chỉ là schema dependency,
không có CRUD endpoint độc lập.

Catalog và OpenAPI đều có index theo `DocType.module` (Accounts, Stock,
Buying, Selling, CRM, Manufacturing...). `typed_modules` quyết định module
nào được phân tích chi tiết; `public_modules` trong contract mới quyết định
module nào được xuất thành API curated. Vì vậy Core, Desk, Setup, Custom và
các module kỹ thuật vẫn có trong catalog nhưng không tự động thành public API.
Public typed route dùng `/api/v1/<module>/<resource>` và được rewrite về
Document API native.

Ngoài artifact tổng hợp, generator tạo OpenAPI riêng tại
`contracts/generated/openapi/modules/<module>.yaml` và `.json`; danh sách file nằm ở
`contracts/generated/openapi/index.json`. Mỗi module file public chỉ chứa typed DocType
của module đó và các child-table dependency cần để schema hợp lệ. Module
technical catalog-only không có file public riêng. Contract hiện tạo 14
module files nghiệp vụ.

Các lifecycle action được khai báo riêng trong `runtime.document_actions`,
không suy đoán từ tên DocType. Ví dụ Sales Invoice có:

```http
POST /api/v1/accounts/sales-invoices/{name}/submit
POST /api/v1/accounts/sales-invoices/{name}/cancel
```

Runtime chuyển hai route này sang `letron_api.api.document_action`; quyền và
validation vẫn do Document controller native của Frappe thực hiện.

RPC có signature được sinh request schema từ annotation; RPC không suy ra được
schema dùng fallback với `x-schema-source: runtime-generic`. Webhook/realtime
chỉ là capability mô tả trong contract, chưa phải delivery consumer thật.

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
    "http://localhost:8080/api/resource/Customer/CUST-0001",
    headers={"Authorization": f"token {api_key}:{api_secret}", "X-Request-Id": request_id},
    timeout=30,
)
response.raise_for_status()
customer = response.json()["data"]
```

```ts
const response = await fetch(`${baseUrl}/api/resource/Customer/CUST-0001`, {
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

Workspace hiện chưa bật webhook delivery riêng và chưa thêm event consumer;
đây là phần tích hợp production tiếp theo, không được giả định rằng realtime
là source of truth.

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
