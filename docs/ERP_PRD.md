# PRD — Letron ERP trên nền tảng ERPNext

## 1. Thông tin tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Sản phẩm | Letron ERP Integration Platform |
| Phiên bản | 1.0 |
| Ngày cập nhật | 2026-08-10 |
| Trạng thái | Phase 1-3 hoàn thành; Phase 4 đang nghiệm thu |
| Product owner | Letron |
| Backend source of truth | ERPNext/Frappe |
| Runtime | Docker Compose |

## 2. Tóm tắt sản phẩm

Letron ERP cung cấp một backend ERP dùng ERPNext/Frappe làm source of truth cho
dữ liệu, schema, permission, validation và business lifecycle. Frontend hoặc
ứng dụng tích hợp gọi API của ERPNext thông qua contract và OpenAPI được quản
lý trong monorepo.

ERPNext và `letron_api` cùng nằm trong monorepo:

```text
apps/erpnext/          # ERPNext source, quản lý bằng Git subtree
apps/letron_api/       # custom Frappe app
lib/api_generator/     # metadata inspector và OpenAPI generator
contracts/             # contract nguồn và artifact sinh ra
docs/                  # PRD, handbook, kiến trúc
tests/                 # test tooling và contract
```

## 3. Vấn đề cần giải quyết

ERPNext có nhiều module, DocType và whitelisted method. Nếu frontend gọi trực
tiếp các endpoint động mà không có contract sẽ dẫn đến:

- khó biết endpoint nào được hỗ trợ;
- schema request/response không rõ ràng;
- tên DocType có khoảng trắng gây URL khó sử dụng;
- không phân biệt API catalog đầy đủ với API curated public;
- khó kiểm tra sự khác nhau giữa source metadata, OpenAPI và runtime;
- khó tái lập runtime trên môi trường khác.

Sản phẩm này giải quyết bằng runtime chuẩn hóa, contract nguồn, catalog đầy đủ,
OpenAPI theo module và handbook có ví dụ sử dụng.

## 4. Mục tiêu sản phẩm

### 4.1. Mục tiêu chính

1. Chạy ERPNext/Frappe ổn định bằng Docker Compose.
2. Cung cấp một API contract có thể dùng trực tiếp cho frontend và hệ thống
   tích hợp.
3. Phản ánh đầy đủ metadata runtime trong catalog.
4. Sinh OpenAPI 3.1 curated theo các module nghiệp vụ được chọn.
5. Giữ mọi write operation đi qua controller, permission và lifecycle native
   của ERPNext.
6. Cho phép đồng bộ phiên bản ERPNext fork bằng Git subtree.

### 4.2. Không phải mục tiêu

- Viết lại business logic của ERPNext.
- Tạo business DocType riêng khi chưa có quyết định nghiệp vụ.
- Xây dựng BFF hoặc API gateway thứ hai.
- Thay thế MariaDB/Redis của Frappe.
- Thiết kế giao diện Next.js.
- Triển khai webhook/realtime delivery consumer khi runtime chưa có consumer
  thật.

## 5. Người dùng và stakeholder

| Nhóm | Nhu cầu |
|---|---|
| Frontend team | Có OpenAPI và ví dụ request cụ thể theo module |
| Integration team | Có catalog đầy đủ, RPC, metadata và error contract |
| ERP operator | Khởi động, kiểm tra và inspect runtime bằng script chuẩn |
| Backend/platform team | Sync ERPNext fork và regenerate artifact có kiểm soát |
| Business owner | ERPNext giữ dữ liệu và lifecycle nghiệp vụ chuẩn |

## 6. Phạm vi phiên bản hiện tại

### Trong phạm vi

- ERPNext/Frappe runtime trên Docker.
- MariaDB, Redis, site initialization và config-driven launcher.
- Custom app `letron_api` cho health, runtime metadata và integration hooks.
- Native Frappe resource API và whitelisted method API.
- Catalog DocType/method đầy đủ từ source metadata.
- OpenAPI aggregate và OpenAPI riêng cho module public.
- Typed CRUD schema cho các module public.
- Clean route theo module, ví dụ:

```text
/api/v1/accounts/sales-invoices
/api/v1/selling/customers
/api/v1/stock/items
```

- Lifecycle action đã có implementation cho Sales Invoice:

```text
POST /api/v1/accounts/sales-invoices/{name}/submit
POST /api/v1/accounts/sales-invoices/{name}/cancel
```

- File upload contract.
- Request ID và idempotency behavior ở lớp integration route.
- Git subtree để quản lý ERPNext trong monorepo.

### Ngoài phạm vi phiên bản hiện tại

- Các workflow nghiệp vụ Letron chưa được mô tả cụ thể.
- Action `amend` chưa có contract/runtime implementation riêng.
- Webhook delivery consumer production.
- Realtime consumer production.
- SSO/JWT production.
- Contract test đầy đủ cho mọi DocType và mọi permission role.

## 7. Nguyên tắc sản phẩm

1. ERPNext là source of truth.
2. Không sửa source ERPNext chỉ để phục vụ OpenAPI generator.
3. Catalog đầy đủ và OpenAPI curated là hai artifact khác nhau.
4. Chỉ module được khai báo trong `public_modules` mới sinh public module path.
5. Không tự suy đoán DocType nghiệp vụ của Letron.
6. Child table là schema dependency, không tự sinh CRUD endpoint độc lập.
7. API write phải đi qua native permission, validation và document controller.
8. Capability chưa có delivery implementation phải được ghi rõ là chưa hoàn
   thành.

## 8. Yêu cầu chức năng

### FR-01 — Runtime

Hệ thống phải khởi tạo được site `frontend` bằng config và Docker Compose, gồm
Frappe, ERPNext, `letron_api`, MariaDB và Redis.

### FR-02 — Health và runtime inspection

Hệ thống phải cung cấp health endpoint và tooling kiểm tra installed apps,
version, DocType metadata, permission và trạng thái runtime.

### FR-03 — Metadata catalog

`lib/api_generator` phải phát hiện:

- DocType và module;
- parent/child table;
- field type, label, required, hidden, read-only;
- Link target, Table target, Select options;
- whitelisted method, HTTP method, guest access, signature và annotation;
- source path tương đối.

Catalog phải bao gồm toàn bộ metadata phát hiện được, không chỉ public API.

### FR-04 — Contract validation

Contract tại [`contracts/erpnext-integration.yml`](../contracts/erpnext-integration.yml)
phải reject:

- kiểu dữ liệu sai;
- DocType hoặc method không tồn tại;
- public module không nằm trong typed module;
- schema collision;
- server URL rỗng hoặc chưa resolve khi generate;
- action không được hỗ trợ.

### FR-05 — OpenAPI generation

Generator phải tạo:

- aggregate OpenAPI;
- OpenAPI theo từng public module;
- schema typed CRUD;
- không công bố resource API hoặc RPC fallback động;
- reusable response, pagination, upload và header components.

Artifact nằm tại:

```text
contracts/generated/catalog.json
contracts/generated/openapi.json
contracts/generated/openapi.yaml
contracts/generated/openapi/modules/
```

### FR-06 — Module routes

Module route phải dùng slug ổn định, không dùng DocType name có khoảng trắng
trong URL. Runtime route resolver và OpenAPI phải dùng cùng quy tắc slug.

### FR-07 — Document lifecycle

Lifecycle action chỉ được public khi có cấu hình contract và implementation
runtime tương ứng. Hiện tại Sales Invoice hỗ trợ `submit` và `cancel`.

### FR-08 — Integration documentation

Handbook phải có base URL, authentication, headers, CRUD, RPC, metadata,
upload, response/error, retry và reconciliation examples.

## 9. Yêu cầu phi chức năng

### NFR-01 — Tính tái lập

Một checkout mới phải có thể cài tooling, generate catalog/OpenAPI và chạy
runtime bằng các lệnh documented.

### NFR-02 — Tính nhất quán

Catalog, OpenAPI, handbook và runtime route không được mô tả các endpoint
khác nhau mà không ghi rõ lý do.

### NFR-03 — Tính kiểm thử

Mỗi thay đổi generator/contract phải chạy được:

```powershell
uv run api-generator validate
uv run api-generator generate
uv run ruff check lib apps/letron_api tests
uv run ty check lib
uv run pytest -q
.\docker-start.ps1 -Action verify
```

### NFR-04 — Tính vận hành

Launcher phải validate config trước khi chạy Docker, không tạo duplicate site/app
không cần thiết và phải expose health endpoint kiểm tra được bằng HTTP.

### NFR-05 — Tương thích ERPNext

ERPNext source phải giữ nguyên logic upstream. Custom integration code nằm ở
`apps/letron_api/`; thay đổi ERPNext phải được review như thay đổi source trong
monorepo.

## 10. API contract model

### Catalog đầy đủ

`contracts/generated/catalog.json` phản ánh toàn bộ DocType và whitelisted
method được inspector phát hiện, kể cả endpoint chưa được chọn làm public
contract.

### OpenAPI curated

`contracts/generated/openapi.json` và `.yaml` chỉ công bố:

- curated Frappe API cần thiết;
- curated whitelisted methods;
- public modules;
- typed CRUD và action đã khai báo;
- metadata/upload contract.

### OpenAPI module

Mỗi file trong `contracts/generated/openapi/modules/` chỉ chứa một public
module và child schema dependency của module đó.

### Webhook/realtime

Contract chỉ mô tả capability hiện có. Khi chưa có delivery consumer thật,
không đánh dấu capability đó là production-complete.

## 11. Acceptance criteria

### Runtime

- Docker `verify` pass.
- Health HTTP trả thành công.
- Site cài `frappe`, `erpnext`, `letron_api`.
- Restart không tạo duplicate site/app.

### Contract/generator

- Generate tạo đủ catalog (813 DocTypes, 1326 whitelisted methods) và OpenAPI.
- OpenAPI 3.1 validator pass với curated resource allowlist.
- Không có dynamic fallback path trong module spec.
- Aggregate chỉ có các operation được allowlist rõ ràng.
- Field numeric/date/link/select/table được map đúng.
- Action path Sales Invoice `submit`/`cancel` dùng HTTP POST và chỉ xuất hiện khi
  có implementation.
- OpenAPI aggregate chỉ public Customer, Quotation, Sales Order và Sales Invoice;
  module artifacts chỉ gồm Accounts và Selling.

### Quality

- Ruff pass.
- ty pass.
- Pytest pass.
- `git diff --check` pass.
- `git submodule status` không còn ERPNext submodule.
- ERPNext source nằm tại `apps/erpnext/` và Docker mount đúng đường dẫn.

## 12. Roadmap

### Phase 1 — Runtime nền tảng — Hoàn thành

- Docker/site/configurator.
- Custom Frappe app.
- Health, runtime info và runtime snapshot.
- Verify/inspect runtime.

### Phase 2 — Catalog và metadata — Hoàn thành

- Inspector DocType/method.
- Field/link/child-table metadata.
- Catalog đầy đủ.
- Contract validation.

### Phase 3 — OpenAPI và handbook — Hoàn thành

- Aggregate OpenAPI.
- Public module OpenAPI cho Accounts và Selling.
- Clean module routes.
- Typed schema và public allowlist có ranh giới rõ.
- Handbook integration.

### Phase 4 — Nghiệm thu integration — Hoàn thành

- Contract test trên Docker cho Customer, Quotation, Sales Order và Sales Invoice.
- CRUD, native Link/child table, permission/error matrix và Invoice submit/cancel.
- Request ID, idempotency, retry/reconciliation và fixture cleanup.
- Runtime snapshot, OpenAPI artifacts và host quality gates đã pass.

### Phase 5 — Mở rộng test API quan trọng — Kế hoạch

Mục tiêu là tăng runtime coverage cho các capability đã có trong contract nhưng
chưa thuộc curated business resources của Phase 4; không test dàn trải toàn bộ
metadata ERPNext.

P0:

- Authentication bằng `Authorization: token api_key:api_secret`, gồm token đúng,
  token sai và thiếu token.
- `health`, `runtime_info`, `runtime_snapshot` và quyền guest/authenticated.
- Curated `/api/v1/...` với list filter/pagination/order/fields,
  detail, create/update/delete và lỗi Link/required/read-only/404.
- `POST /api/method/upload_file` với upload hợp lệ, thiếu file, auth và cleanup.
- Chain nghiệp vụ Quotation → Sales Order → Sales Invoice, gồm Link validation
  và native lifecycle.

P1:

- Unicode/URL encoding, response schema list/detail và error envelope.
- Idempotency retry sau validation error và concurrent duplicate write.
- Read-after-timeout theo business key/name và reconciliation evidence.
- Permission matrix cho từng nhóm resource và action.

Acceptance Phase 5:

- Tất cả P0 pass trên Docker runtime qua native Frappe API.
- Không có fixture, file upload, stale Link hoặc credential trong artifact.
- OpenAPI aggregate/module paths khớp runtime; catalog không suy giảm.
- `pytest`, Ruff, ty, `git diff --check` và runtime verify pass.
- Webhook/realtime chỉ được đưa vào acceptance khi có delivery consumer thực tế;
  trước thời điểm đó chỉ kiểm tra capability declaration và không gọi là delivery pass.

## 13. Tài liệu liên quan

- [Integration contract](../contracts/erpnext-integration.yml)
- [Integration handbook](ERPNext_Integration_Handbook.md)
- [README — ERPNext trong monorepo](../README.md)
- [System architecture](System_Architecture.md)
