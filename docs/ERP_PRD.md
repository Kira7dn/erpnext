# PRD — Letron ERP trên nền tảng ERPNext

## 1. Thông tin tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Sản phẩm | Letron ERP Integration Platform |
| Phiên bản | 1.0 |
| Ngày cập nhật | 2026-08-12 |
| Trạng thái | Phase 1-7 và production implementation hoàn thành; Ubuntu clean-checkout evidence còn chờ |
| Product owner | Letron |
| Backend source of truth | ERPNext/Frappe |
| Runtime | Docker Compose |

## 2. Tóm tắt sản phẩm

Letron ERP cung cấp một backend ERP dùng ERPNext/Frappe làm source of truth cho
dữ liệu, schema, permission, validation và business lifecycle. Frontend hoặc
ứng dụng tích hợp gọi API của ERPNext thông qua contract và OpenAPI được quản
lý trong monorepo.

Sản phẩm là headless: không cung cấp ERPNext Desk hoặc setup wizard cho người
vận hành. Một deployment unit của Letron gồm đúng một Docker Compose project,
một Frappe site, một tenant và một Company. Mọi bước khởi tạo Company, Chart of
Accounts, tax, defaults và policy phải được `letron_api` điều phối bằng API hoặc
one-shot service; không có bước cấu hình thủ công qua UI.

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
7. Khởi tạo đầy đủ một tenant/Company qua API để business API dùng được ngay,
   không phụ thuộc Desk/setup wizard.
8. Quản lý toàn bộ business configuration native của ERPNext/Frappe bằng
   `config/policy.yaml`, có completeness và drift gate fail-closed.

### 4.2. Không phải mục tiêu

- Viết lại business logic của ERPNext.
- Tạo business DocType riêng khi chưa có quyết định nghiệp vụ.
- Xây dựng BFF hoặc API gateway thứ hai.
- Thay thế MariaDB/Redis của Frappe.
- Cung cấp ERPNext Desk, setup wizard hoặc bất kỳ giao diện cấu hình vận hành
  nào; sản phẩm chỉ có API.
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
- Ràng buộc một site bằng đúng một tenant và một Company.
- Headless tenant bootstrap qua `letron_api`, dùng controller và country fixture
  native của ERPNext.
- Policy control plane để đọc, validate, plan và apply `config/policy.yaml`.
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
9. Một Letron ERP instance không được tạo Company thứ hai dù ERPNext upstream
   hỗ trợ multi-company.
10. Không có UI fallback: chức năng chỉ hoàn thành khi có API/bootstrap path và
    acceptance chạy được hoàn toàn headless.
11. `config/config.yaml` chỉ quản lý system/runtime; entity và transaction nằm
    trong ERPNext DB; secret nằm trong `.env`; mọi business configuration native
    thuộc `config/policy.yaml`.
12. Policy coverage phải fail-closed: DocType, field hoặc nguồn fixture/config
    upstream chưa phân loại không được âm thầm bỏ qua.

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

### FR-09 — Headless tenant bootstrap

Một site mới chỉ khởi động backend sau khi `letron_api` hoàn tất bootstrap.
Input bootstrap nằm trong `config/policy.yaml`, gồm tên pháp nhân,
abbreviation, country, currency, domain và lựa chọn Chart of Accounts; thao tác
phải idempotent và từ chối tạo Company thứ hai.

Control plane hiện tại gồm:

```text
policy-bootstrap (Docker one-shot service)
GET  /api/method/letron_api.api.health
GET  /api/method/letron_api.api.runtime_snapshot
GET  /api/method/letron_api.config_control.get_configuration?kind=policy
PUT  /api/method/letron_api.config_control.put_configuration
```

Bootstrap không nhận một request body riêng và không có đường ghi thứ hai:
Company desired state luôn được đọc từ `policy.yaml`. One-shot service và hai
method health/snapshot không làm tăng curated public business operation count.

Bootstrap phải tạo Company qua controller native để ERPNext tự tạo Chart of
Accounts, default Accounts, Cost Center, Warehouse và country fixtures. Với
`country: Vietnam`, luồng native phải đọc
`erpnext/setup/setup_wizard/data/country_wise_tax.json`; phiên bản ghim hiện
khai báo `Vietnam Tax` với account `VAT` và `tax_rate: 10`. Kết quả phải là
Account và Sales/Purchase/Item Tax Template native có readback xác nhận, không
phải record shadow của `letron_api`.

Không được yêu cầu người dùng mở Desk, setup wizard hoặc chạy lệnh bench thủ
công. Bootstrap lỗi phải rollback/fail-closed và để site ở trạng thái chưa sẵn
sàng.

### FR-10 — Full native policy wrapper

`config/policy.yaml` phải là desired-state SOT cho toàn bộ business
configuration native của ERPNext/Frappe sau bootstrap. Wrapper chỉ điều phối
native DocType/controller; không tạo policy engine hoặc bảng dữ liệu song song.

Coverage không được chỉ quét `doctype/*.json`. Inventory phải bao gồm tối thiểu:

- DocType và child-DocType metadata của Frappe/ERPNext;
- persistent Single settings và non-Single rule/template/workflow/permission;
- setup-wizard data, gồm country tax data;
- Chart-of-Accounts templates và regional fixtures/hooks có sinh business
  configuration;
- effective policy documents đang tồn tại trong MariaDB.

Mỗi nguồn, DocType và field phải được quản lý hoặc bị loại bằng classification
và lý do tường minh. Giá trị `true`, `false`, `0`, `null`, chuỗi/list rỗng,
Unicode và child row phải được giữ theo native field type. Có mục chưa phân loại,
record policy ngoài YAML, field mới hoặc runtime drift thì validate/readiness
phải fail.

Policy control-plane API phải ghi file atomic với optimistic hash, validate,
apply trong transaction, native readback và rollback khi lỗi. Managed policy
không được sửa bằng generic resource API. Thay đổi thành công phải tồn tại cả
trong YAML bind-mounted trên compute và native ERPNext DB.

## 9. Yêu cầu phi chức năng

### NFR-01 — Tính tái lập

Một checkout mới phải có thể cài tooling, generate catalog/OpenAPI và chạy
runtime bằng các lệnh documented.

### NFR-02 — Tính nhất quán

Catalog, OpenAPI, handbook và runtime route không được mô tả các endpoint
khác nhau mà không ghi rõ lý do.

### NFR-03 — Tính kiểm thử

Mỗi thay đổi generator/contract phải chạy được:

Các action trong gate này là tooling nội bộ. Giao diện triển khai production
chỉ dùng `.\docker-start.ps1` không có flag.

```powershell
uv run python -m lib.api_generator generate
uv run python -m lib.api_generator check
uv run openapi-spec-validator contracts/openapi/public.yaml
uv run openapi-spec-validator contracts/openapi/control-plane.yaml
uv run ruff check staging_consumer.py lib apps/letron_api/letron_api tests
uv run ty check staging_consumer.py lib apps/letron_api/letron_api tests
uv run pytest -m "not integration" -q
.\docker-start.ps1 -Action verify
```

### NFR-04 — Tính vận hành

Launcher phải validate config trước khi chạy Docker, không tạo duplicate site/app
không cần thiết và phải expose health endpoint kiểm tra được bằng HTTP.

### NFR-05 — Tương thích ERPNext

ERPNext source phải giữ nguyên logic upstream. Custom integration code nằm ở
`apps/letron_api/`; thay đổi ERPNext phải được review như thay đổi source trong
monorepo.

### NFR-06 — Readiness fail-closed

Business API chỉ được báo ready khi site có đúng một Company, bootstrap đã hoàn
tất, policy compatibility khớp phiên bản ghim và policy drift bằng 0. Thiếu
Company, có nhiều Company, thiếu prerequisite hoặc có config chưa phân loại đều
phải trả trạng thái không sẵn sàng với lỗi có thể audit.

### NFR-07 — Tái lập tenant

Với cùng bootstrap input, `config.yaml`, `policy.yaml` và secret environment,
một site sạch phải tạo ra cùng effective business configuration. Round-trip
`apply → export` phải canonical-equal và apply lần hai phải không thay đổi dữ
liệu.

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

### Public resource matrix

| Module | Parent resource public | Lifecycle public |
|---|---|---|
| Accounts | Sales Invoice, Purchase Invoice, Payment Entry | submit/cancel cho hai Invoice |
| Buying | Supplier, Purchase Order | submit/cancel cho Purchase Order |
| Contacts | Address, Contact | không có; `Dynamic Link` chỉ là child schema |
| Selling | Customer, Quotation, Sales Order, Delivery Note | submit/cancel cho Sales Order |
| Stock | Item, Warehouse, Material Request, Purchase Receipt, Stock Entry, Item Price | submit/cancel cho Material Request, Purchase Receipt và Stock Entry |

Stock Reconciliation, Serial No, Batch, Bin và Stock Ledger Entry không thuộc
public contract phase này. Ledger chỉ được tạo bởi lifecycle native ERPNext.

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

### Headless bootstrap

- Site sạch báo `bootstrap_required`; business API chưa ready.
- Bootstrap hoàn thành hoàn toàn qua API/one-shot service, không dùng Desk hoặc
  thao tác bench thủ công.
- Sau bootstrap có đúng một Company; request lặp lại idempotent và request tạo
  Company thứ hai bị từ chối.
- Company Việt Nam có VND, Chart of Accounts, default Accounts, Cost Center và
  Warehouse native.
- Native Vietnam fixture tạo `Vietnam Tax` với rate `10` trong Sales, Purchase
  và Item Tax Template; thử nghiệm Sales/Purchase Invoice xác nhận calculation
  và GL qua lifecycle native.
- Bootstrap lỗi không để Company/Account/Tax Template dở dang và site vẫn
  không ready.

### Policy completeness

- Inventory bao phủ DocType metadata, child tables, setup-wizard country data,
  Chart-of-Accounts templates, regional fixtures/hooks và effective DB records.
- `unclassified_sources`, `unclassified_doctypes`, `unclassified_fields`,
  `unmanaged_policy_records`, `schema_drift`, `runtime_drift` và
  `roundtrip_diff` đều bằng `0`.
- Test giữ nguyên `true`, `false`, `0`, `null`, chuỗi/list rỗng, Unicode và child
  tables.
- Policy API update file bind-mounted và native DB atomically; lỗi validation
  hoặc controller rollback cả hai phía.
- Site sạch `apply → export` canonical-equal; apply lần hai trả `applied: 0`.
- ERPNext/Frappe đổi phiên bản hoặc thêm config source/field chưa phân loại làm
  validation và readiness fail.

### Contract/generator

- Generate tạo đủ catalog (814 DocTypes, 1327 whitelisted methods) và OpenAPI.
- OpenAPI 3.1 validator pass với curated resource allowlist.
- Không có dynamic fallback path trong module spec.
- Aggregate chỉ có các operation được allowlist rõ ràng.
- Field numeric/date/link/select/table được map đúng.
- Action `submit`/`cancel` dùng HTTP POST và chỉ xuất hiện cho resource có
  implementation runtime rõ ràng.
- OpenAPI aggregate có đúng 137 operation, tất cả `passed`; module artifacts
  public gồm Accounts, Buying, Contacts, Selling và Stock với status/evidence
  giống aggregate.

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
- Public module OpenAPI cho Accounts, Buying, Contacts, Selling và Stock.
- Clean module routes.
- Typed schema và public allowlist có ranh giới rõ.
- Handbook integration.

### Phase 4 — Nghiệm thu integration — Hoàn thành

- Contract test trên Docker cho Customer, Quotation, Sales Order và Sales Invoice.
- CRUD, native Link/child table, permission/error matrix và Invoice submit/cancel.
- Request ID, idempotency, retry/reconciliation và fixture cleanup.
- Runtime snapshot, OpenAPI artifacts và host quality gates đã pass.

### Phase 5 — Mở rộng test API quan trọng — Hoàn thành

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
- Webhook/realtime đã pass với staging consumer Docker, HMAC, dedupe, reconnect
  và delivery polling tối đa 180 giây.

### Phase 6 — Contacts và Stock core — Hoàn thành

- Public CRUD cho Address, Contact, Material Request, Purchase Receipt, Stock
  Entry và Item Price; `Dynamic Link` chỉ là child schema.
- Customer/Supplier → Address/Contact; Material Request → Purchase Order →
  Purchase Receipt; Stock Entry receipt/issue/transfer; Item → Item Price.
- Material Request, Purchase Receipt và Stock Entry dùng submit/cancel native;
  Purchase Receipt liên kết Purchase Order đã submit và stock ledger chỉ phát
  sinh qua controller ERPNext.
- Docker acceptance xác nhận persistence, delete→404, list controls, auth,
  permission, Link/required validation, Unicode, delivery và cleanup fail-closed.
- OpenAPI kết thúc ở `{passed: 103, partial: 0, not-tested: 0, blocked: 0}`.

### Phase 7 — Accounts operational core — Hoàn thành

Mục tiêu là hoàn thiện lớp chứng từ và master vận hành Accounts trước khi mở
CRM, Buying hoặc các module nghiệp vụ khác. Mọi write tiếp tục đi qua Document
controller native; không tạo API ghi trực tiếp ledger. Manufacturing không
thuộc roadmap public API hiện tại.

Public resource mới:

| Resource | Route | Phạm vi |
|---|---|---|
| Bank | `/api/v1/accounts/banks` | list/create/detail/update/delete |
| Bank Account | `/api/v1/accounts/bank-accounts` | list/create/detail/update/delete |
| Mode of Payment | `/api/v1/accounts/modes-of-payment` | list/create/detail/update/delete |
| Cost Center | `/api/v1/accounts/cost-centers` | CRUD parent; giữ invariant tree native |
| Journal Entry | `/api/v1/accounts/journal-entries` | CRUD và submit/cancel native |
| Payment Request | `/api/v1/accounts/payment-requests` | CRUD và submit/cancel native |

Contract đã tăng 34 operation: 30 CRUD operation và bốn lifecycle action.
Aggregate và module Accounts có cùng evidence, tổng đúng 137 operation với
`{passed: 137, partial: 0, not-tested: 0, blocked: 0}`. Các operation mới khởi
đầu ở `not-tested` và chỉ được chuyển `passed` sau Docker acceptance.

Luồng acceptance chính:

- Bank → Bank Account, liên kết Company và Account thật khi payload sử dụng
  company ledger account.
- Mode of Payment → child account mapping theo Company.
- Cost Center tạo parent/child, update/readback và xóa leaf trước root; không
  phá invariant NestedSet.
- Journal Entry dùng account thật, tổng debit bằng tổng credit; draft update và
  delete tách khỏi fixture submit/cancel.
- Payment Request loại `Outward` liên kết Purchase Invoice đã submit; draft,
  delete và lifecycle dùng ba Purchase Invoice riêng.
- Tất cả list kiểm tra `fields`, `filters`, `order_by`, `limit_start` và
  `limit_page_length`; mọi delete dùng fixture disposable và GET sau delete trả
  `404`.
- Kiểm tra guest `401/403`, role permission native, required field, invalid
  Link/Dynamic Link, imbalance Journal Entry, Unicode/URL và idempotency.
- Webhook/realtime polling tối đa 180 giây; mọi outbox của run phải `Delivered`.

Evidence gần nhất: launcher production không flag và `verify` pass; toàn bộ integration đạt
`5 passed, 49 deselected`; host đạt `52 passed, 5 deselected`; Ruff, ty,
contract validation, OpenAPI generate/validate và `git diff --check` pass.
Journal Entry submit tạo GL active và cancel xóa toàn bộ GL active; Payment
Request xác nhận `docstatus` 1→2 và `Initiated`→`Cancelled` bằng permission
submit native của Accounts Manager.

Cleanup và hard gates:

- Cancel chứng từ submitted trước delete; dọn GL Entry, Payment Ledger Entry,
  outbox, consumer event và Cost Center tree theo prefix.
- Audit fail-closed không còn `ACCEPTANCE-LOCAL-*`, File, Journal Entry, Payment
  Request, Cost Center, GL/Payment Ledger hoặc consumer event residue.
- Chạy `pytest`, Ruff, ty, contract validation, OpenAPI generate/validate,
  `git diff --check`, launcher `config/up/verify` và toàn bộ Docker integration.

Không thuộc Phase 7:

- Không public CRUD cho Account, GL Entry, Payment Ledger Entry hoặc bất kỳ
  ledger table nào.
- Bank Transaction, Bank/Payment Reconciliation, Payment Order, Budget, POS,
  Subscription và báo cáo read-only được thiết kế ở increment Accounts kế tiếp.
- Không dùng generic resource/RPC fallback và không sửa source ERPNext.

### Headless single-tenant bootstrap và policy SOT — Native baseline hoàn thành

`config/config.yaml` là SOT UTF-8 cho system/runtime và `config/policy.yaml` là
SOT UTF-8 cho policy; cả hai được version-control và tồn tại sẵn trên compute.
Mô hình đích bắt buộc một Docker project/Frappe site bằng đúng một tenant và
một Company. Sản phẩm không có Desk/setup wizard; bootstrap và mọi thay đổi
policy phải có API/one-shot path của `letron_api`.

ERPNext upstream đã có native country bootstrap cho Việt Nam tại
`erpnext/setup/setup_wizard/data/country_wise_tax.json`, hiện định nghĩa
`Vietnam Tax`, account `VAT`, `tax_rate: 10`. `Company.on_update` gọi native
country fixture và tax setup khi tạo Company/Chart of Accounts. Letron phải tái
sử dụng đúng server-side controller này trong headless bootstrap, rồi quản lý
effective configuration sinh ra bằng `policy.yaml`; không yêu cầu UI và không
tự dựng tax record shadow.

Native baseline hiện đã đạt: `policy-bootstrap` đọc Company từ `policy.yaml`,
tạo đúng một Company bằng controller native với Standard Chart of Accounts và
country fixture Việt Nam, rồi materialize ba tax template native vào cùng
bundle. Runtime readback có Sales/Purchase/Item Tax Template `Vietnam Tax -
LTVN` ở mức 10%; chạy bootstrap lần hai không tạo thêm dữ liệu. Site có nhiều
Company hoặc Company khác YAML bị từ chối. JSON inventory chỉ quét
`doctype/*.json` vẫn không đủ để chứng minh full coverage vì bỏ sót
country/setup-wizard data.

Wrapper `letron_api.policy` thực hiện bootstrap bundle, export, validate, plan,
apply và readback. Phạm vi dữ liệu thực tế gồm 15 document: 12 Single DocType
Settings và ba tax template native của Việt Nam. Default Role/User/Fiscal
Year/Workflow vocabulary và Settings
module chưa dùng không được auto-export. Workflow, Custom DocPerm, User Permission,
Authorization Rule, Accounting Dimension và các business rule/template native
đã được wrapper allowlist nhưng runtime hiện có 0 record. Tax rule/template, payment terms, pricing, shipping, SLA và
print/email/notification policy chưa được gom. Inventory source/storage được
chốt tại `docs/Configuration_Inventory.md`.
Password, API secret, metadata phát sinh và business transaction/master không
được đưa vào bundle.

Secret thật nằm trong `.env` bị Git ignore; YAML chỉ chứa `${ENV_NAME}`. Docker
chạy one-shot `policy-bootstrap`, `config-sync`, rồi `policy-sync` sau migrate
và trước backend/workers.
Managed field không được sửa trực tiếp qua Desk hoặc generic resource API;
migration được phép chạy rồi YAML được apply lại. Health/runtime snapshot công bố version, SHA-256 và
drift count; scheduler audit và launcher `verify` fail-closed khi database lệch
SOT. System Manager có control-plane API fixed-path để đọc/ghi atomic đúng một
trong hai YAML với optimistic hash và apply/readback; API không resolve secret,
không cho chọn path tùy ý và không thuộc public business contract. Vì vậy
contract vẫn đúng 23 resource/137 operation.

Acceptance đã chứng minh đúng một Company, native Vietnam tax 10% ở cả ba
template, native readback khớp YAML, direct edit bị từ chối, drift trực tiếp
được phát hiện, apply phục hồi zero drift và apply lần hai trả `applied: 0`
trong phạm vi 15 document; evidence này chưa chứng minh full policy coverage.
Toàn bộ Phase 7
CRUD/lifecycle/delivery/cleanup vẫn pass và không được dùng để thay thế các gate
bootstrap/policy mới ở mục 11.

### Thứ tự sau Phase 7

1. Full policy coverage: inventory mọi native config source, classification
   không còn unknown, typed round-trip và atomic Policy API.
2. Accounts banking/reconciliation: Bank Transaction, Payment Reconciliation,
   Payment Order và các action đối soát có contract riêng. Account, GL Entry và
   Payment Ledger Entry chỉ được cân nhắc read-only; tuyệt đối không public CRUD.
3. CRM/Buying trước đơn hàng: Lead, Opportunity, Request for Quotation và
   Supplier Quotation.
4. Stock control/traceability: Stock Reconciliation, Serial No, Batch, Quality
   Inspection, Pick List, Shipment, Landed Cost Voucher và Stock Reservation
   Entry; ledger vẫn chỉ phát sinh qua controller native.
5. Assets/Maintenance, Projects/Timesheet và Support/Warranty chỉ mở theo nhu
   cầu tích hợp đã được xác nhận.

Manufacturing, gồm BOM, Production Plan, Work Order và Job Card, bị loại khỏi
roadmap hiện tại. Budget, POS và Subscription cũng chưa được ưu tiên; mỗi nhóm
chỉ được đưa vào phase mới khi có use case và acceptance contract riêng.

## 13. Audit bàn giao API, config và policy

### Kết luận audit

Ngày audit: 2026-08-12.

Business API và production implementation **đã đủ điều kiện bàn giao trên
Windows/Docker Linux đã kiểm chứng**. Tám blocker P0 đã được đóng bằng code và
test. Trạng thái đa nền tảng chưa ký hoàn tất vì chưa chạy clean-checkout
acceptance trực tiếp trên máy Ubuntu thật.

| Hạng mục | Kết quả |
|---|---|
| Curated business API | Đạt trong phạm vi 5 module, 23 resource, 137 operation |
| Acceptance | `{passed: 137, partial: 0, not-tested: 0, blocked: 0}` |
| Native permission/controller/lifecycle | Đạt trong phạm vi công bố |
| Config và policy SOT | Đạt: invariant liên file, immutable Company và rollback bù |
| OpenAPI handoff | Đạt: public/control-plane artifact có checksum |
| Launcher/runtime profile | Đạt trên Windows/Docker Linux; Ubuntu host còn chờ evidence |
| Tài liệu tích hợp | Đạt: onboarding, role matrix, config-control và webhook runbook |

Phạm vi đã xác nhận gồm explicit `/api/v1` allowlist, không có generic
resource/RPC fallback, write qua controller native, Accounts operational core,
durable outbox với HMAC/retry/dedupe và hai YAML SOT không chứa secret.
Kết quả này chỉ xác nhận policy đã khai báo, không chứng minh `policy.yaml` đã
bao phủ toàn bộ policy native của ERPNext.

### Kết quả đóng blocker P0

| ID | Kết quả implementation | Trạng thái |
|---|---|---|
| P0-1 | `contracts/openapi/` giữ public/control-plane YAML+JSON và manifest checksum; generator có `check` | Đóng |
| P0-2 | Control-plane spec typed riêng, không làm tăng 137 business operation | Đóng |
| P0-3 | Công bố 400/401/403/404/409/417/429/500, typed error; idempotency chỉ trên write | Đóng |
| P0-4 | PUT rollback chính xác YAML/runtime; Docker negative test xác nhận hash và zero drift | Đóng |
| P0-5 | `bootstrap.company` immutable sau initialization, conflict trả 409 | Đóng |
| P0-6 | Combined validator chạy ở launcher, control API, bootstrap, sync và health | Đóng |
| P0-7 | Config v2 production-like, MariaDB-only, staging override riêng, delivery enable thật, backup/restore native | Đóng |
| P0-8 | Launcher không flag chờ tối đa 180 giây, zero drift, health và restart acknowledgement | Code đóng; Windows pass, Ubuntu host chờ chạy |

### Kết quả P1 cho team tích hợp tự phục vụ

1. Handbook đã có issue/rotate/revoke API key và role khởi điểm theo module.
2. Control-plane có typed request/response, conflict và rollback semantics.
3. Webhook có runbook HMAC, dedupe, replay và pull reconciliation.
4. Container preflight đã chứng minh bind mount atomic-writable; Ubuntu checkout
   sạch vẫn là bước evidence ngoài môi trường Windows hiện tại.
5. Health typed, idempotency chỉ trên write, discovery được tách khỏi public.
6. Bootstrap production dùng `letron_api.tenant_bootstrap`; tên seed cũ đã bỏ.

### Điều kiện đổi trạng thái sang production ready

- P0-1 đến P0-8 có implementation và test.
- Curated OpenAPI artifact/version dùng được mà không cần kiến thức nội bộ.
- Clean Ubuntu deployment bằng một lệnh chỉ thành công sau zero drift và HTTP
  health.
- Negative test config-control chứng minh rollback cả file và DB.
- Integration-user/role và webhook recovery runbook đã được diễn tập.
- Host gates, Docker integration, OpenAPI validation và residue cleanup pass
  trên đúng revision bàn giao.

Evidence thực tế trên revision hiện tại:

- host: `52 passed, 5 deselected`; Ruff và ty pass;
- Docker integration: `5 passed, 49 deselected`;
- OpenAPI public/control-plane đều validate, manifest lần lượt 137 và 2 operation;
- backup tạo config/DB/public/private và restore drill pass, site tạm cleanup;
- `docker-start.ps1` không flag pass production health, zero drift và loại staging consumer.

Trạng thái chính thức tại thời điểm audit:

```text
Business API integration:                 READY
Production implementation on Windows:    READY
Cross-platform Ubuntu handoff signature: PENDING CLEAN-HOST EVIDENCE
```

## 14. Tài liệu liên quan

- [Integration contract](../contracts/erpnext-integration.yml)
- [Integration handbook](Integration_Handbook.md)
- [README — ERPNext trong monorepo](../README.md)
- [System architecture](System_Architecture.md)
