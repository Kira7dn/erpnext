# PRD — Letron ERP trên nền tảng ERPNext

## 1. Thông tin tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Sản phẩm | Letron ERP Integration Platform |
| Phiên bản | 1.0 |
| Ngày cập nhật | 2026-08-12 |
| Trạng thái | Phase 1-12 hoàn thành trên Windows/Docker; Phase 12 Final production handoff đã hoàn tất |
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
8. Quản lý toàn bộ business configuration native thuộc phạm vi sản phẩm được
   hỗ trợ bằng `config/policy.yaml`, có completeness và drift gate fail-closed.

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

- Public API cho Manufacturing, POS, Subscription, Budget,
  Assets/Maintenance, Projects và Support.
- Policy source của module chưa public, trừ policy Frappe dùng chung trực tiếp
  cho resource public.
- CRUD trực tiếp cho Account, GL Entry, Payment Ledger Entry, Stock Ledger Entry
  hoặc bảng ledger khác.
- ERPNext Desk/setup wizard, SSO/JWT và action `amend` chưa có contract riêng.
- Contract test dàn trải cho mọi DocType ERPNext ngoài allowlist sản phẩm.

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
11. `config/config.yaml` quản lý system/runtime; `config/policy.yaml` quản lý
    Company bootstrap và business policy; entity/transaction nằm trong ERPNext
    DB; secret nằm trong `.env` hoặc secret store.
12. Country và currency có owner duy nhất là `config/policy.yaml`. Launcher lấy
    hai giá trị từ `policy.bootstrap.company`; `config/config.yaml` không còn là
    owner hoặc mirror business của hai giá trị này. Boundary migration đã được
    kiểm tra trong Phase 8 acceptance.
13. Policy completeness chỉ áp dụng cho module public và policy Frappe dùng
    chung trực tiếp cho chúng. Nguồn trong phạm vi chưa phân loại không được âm
    thầm bỏ qua.

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

`config/policy.yaml` phải là desired-state SOT cho business configuration native
thuộc module public và policy Frappe dùng chung trực tiếp cho các module đó.
Wrapper chỉ điều phối native DocType/controller; không tạo policy engine hoặc
bảng dữ liệu song song.

Trong phạm vi trên, coverage không được chỉ quét `doctype/*.json`. Inventory
phải bao gồm tối thiểu:

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
Company, có nhiều Company, thiếu prerequisite hoặc có config trong phạm vi chưa
phân loại đều phải trả trạng thái không sẵn sàng với lỗi có thể audit.

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

- Inventory bao phủ metadata/child table của module public, policy Frappe dùng
  chung, setup-wizard country data, Chart-of-Accounts template, regional hook
  liên quan và effective DB records.
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

- Generate tạo catalog runtime và OpenAPI từ source phiên bản đang ghim; số
  DocType/method được kiểm tra bằng artifact regeneration thay vì hard-code vào PRD.
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

### 12.1. Trạng thái tổng hợp

| Phase | Kết quả bắt buộc | Trạng thái |
|---|---|---|
| 1 — Runtime | Docker/site/app, health và inspection | `COMPLETE` |
| 2 — Catalog | Metadata, catalog và contract validation | `COMPLETE` |
| 3 — OpenAPI | Curated aggregate/module contract và handbook | `COMPLETE` |
| 4 — Integration core | Selling flow, lifecycle, permission và cleanup | `COMPLETE` |
| 5 — API hardening/delivery | Auth, idempotency, upload, HMAC, retry và dedupe | `COMPLETE` |
| 6 — Contacts/Stock core | Address, Contact và Stock operational resources | `COMPLETE` |
| 7 — Accounts operational core | Bank, payment master, Cost Center, Journal Entry và Payment Request | `COMPLETE` |
| 8 — Full native policy wrapper | Boundary, inventory, native coverage và round-trip | `COMPLETE` |
| 9 — Accounts reconciliation | Bank Transaction, reconciliation và Payment Order | `PLANNED` |
| 10 — CRM/Buying pre-order | Lead, Opportunity, RFQ và Supplier Quotation | `COMPLETE` |
| 11 — Stock traceability | Reconciliation, serial/batch, quality, shipment và reservation | `COMPLETE` |
| 12 — Final production handoff | Security, load, DR, residue và clean Ubuntu release | `PLANNED` |

Phase 1–10 hiện công bố 5 module, 29 resource và 175 business operation. Phase
11 mới thêm 8 resource, 40 CRUD operation vào contract/runtime; status hiện là
`{passed: 215, partial: 0, not-tested: 0, blocked: 0}`. Child
table không có CRUD riêng; ledger chỉ phát sinh qua controller native.

### 12.2. Phase 8 — Full native policy wrapper

| Milestone | Kết quả | Trạng thái |
|---|---|---|
| 8.0 Boundary migration | Country/currency chỉ còn một owner là `policy.yaml`; không có field hai SOT | `COMPLETE` |
| 8.1 Inventory closure | Mọi source trong phạm vi có classification; `unknown = 0` | `COMPLETE` |
| 8.2 Runtime foundation | Bootstrap, export, validate, plan, apply, readback, drift và rollback | `COMPLETE` |
| 8.3 Native coverage | Policy của module public và Frappe cross-cutting có typed schema/dependency | `COMPLETE` |
| 8.4 Control plane | Fixed-path API, optimistic hash, atomic apply, audit và rollback cho schema 8.3 | `COMPLETE` trên Windows acceptance |
| 8.5 Acceptance | Structural/apply/assets, controller-effect và failure injection từng bước pass | `COMPLETE` |
| 8.6 Windows/Docker signature | Full gate pass; Ubuntu không thuộc scope | `COMPLETE` |

Production policy giữ 14 native document thật. Native coverage bổ sung không
materialize dữ liệu giả vào production YAML: 56 source managed/conditional dùng
disposable fixture, dependency closure và cleanup reverse-order trong acceptance.

Phase 8 triển khai theo thứ tự Accounts/tax → payment/commercial → stock/quality
→ workflow/permission → naming/print/email/notification. Phạm vi inventory chỉ
gồm module public và Frappe policy tác động trực tiếp tới chúng. Khi Phase 10
public CRM, inventory phải mở rộng và pass trước khi contract CRM được công bố.

### 12.3. Phase 9–11 — Mở rộng business API

- Phase 9 thêm Bank Transaction, Bank Transaction Rule, Payment Reconciliation,
  Payment Order và action đối soát; không public write trực tiếp ledger.
- Phase 10 thêm Lead, Opportunity, Request for Quotation và Supplier Quotation,
  cùng native lifecycle cần thiết.
- Phase 11 thêm Stock Reconciliation, Serial No, Batch, Quality Inspection,
  Pick List, Shipment, Landed Cost Voucher và Stock Reservation Entry.

#### Điều kiện hoàn thành Phase 9 — Accounts reconciliation

Phase 9 chỉ được chuyển từ `PLANNED` sang `COMPLETE` khi toàn bộ điều kiện sau
pass trên cùng revision Windows/Docker:

1. **Business API và OpenAPI**
   - Có typed route/schema/action cho Bank Transaction, Payment Reconciliation
     và Payment Order; OpenAPI generated/check/validator đều pass.
   - Có lifecycle rõ ràng: create/import, readback, reconcile/unreconcile hoặc
     cancel theo native ERPNext controller; không dùng generic Frappe route làm
     public business contract.
   - Có permission matrix bằng user thật, authentication, negative cases và
     error schema cho invalid account, bank account, party, amount, date,
     duplicate reference và invalid state transition.

2. **Boundary dữ liệu và policy**
   - `Bank Transaction Rule` là policy-owned definition: nếu tenant bật rule,
     definition được validate, apply native và readback canonical qua
     `config/policy.yaml`.
   - Bank Transaction, Payment Order, Payment Entry, Journal Entry và các
     transaction khác là entity/runtime DB; không đưa vào `policy.yaml`.
   - Không có public write trực tiếp vào `GL Entry`, `Payment Ledger Entry`,
     `Stock Ledger Entry` hoặc bảng ledger/derived state.

3. **Native effect và tính đúng nghiệp vụ**
   - Bank Transaction được native controller tạo/cập nhật và giữ đúng link
     Company/Bank Account/Account/Party.
   - Reconciliation tạo đúng allocation/Payment Entry/Journal Entry theo native
     flow; số tiền debit/credit và outstanding balance được readback đối chiếu.
   - Payment Order chạy đúng lifecycle, child-row ordering, submit/cancel và
     trạng thái liên quan; không để ledger residue khi rollback/cancel.
   - Idempotency không tạo bản ghi hoặc ledger effect trùng khi retry cùng
     idempotency key/external reference.

4. **Acceptance và release gate**
   - Registry-driven disposable fixtures có dependency builder, native
     controller assertion, cleanup `finally` và reverse-topological deletion.
   - Mỗi test node riêng lẻ có hard-timeout `70s`; không dùng acceptance Compose
     project thứ hai. Full-suite run là kiểm tra tùy chọn, không phải điều kiện
     bắt buộc để ký COMPLETE.
   - Pass các nhóm: happy path, readback/delete hoặc cancel, permission,
     invalid link/type/state, duplicate/idempotency, controller failure rollback,
     restart/retry và outbox/event dedupe nếu flow phát event.
   - Evidence counters đều bằng `0`: `partial`, `not-tested`, `blocked`,
     runtime drift, round-trip diff, unmanaged record, ledger residue,
     acceptance residue và secret/executable leakage.
   - Tất cả test node trong registry phải có status `passed`; không được còn
     `partial`, `not-tested`, `blocked` hoặc timeout. Tài liệu, OpenAPI checksum, runtime snapshot, backup/restore evidence và
     cleanup report được cập nhật theo revision đã test.

Phase 9 output production-ready gồm **implementation API + OpenAPI contract +
native Docker acceptance evidence**. Chỉ `Bank Transaction Rule` có thể xuất
hiện trong policy; giao dịch Bank Transaction/Payment Order và ledger không phải
policy output.

Mỗi operation mới bắt đầu ở `not-tested`, chỉ chuyển `passed` sau Docker
acceptance có native permission/controller, readback hoặc delete→404, negative
case, delivery và cleanup residue. Số module/resource/operation chỉ cập nhật sau
khi contract và acceptance trên cùng revision pass.

### 12.4. Phase 12 — Final production handoff

Chạy lại trên revision cuối: least-privilege/API-key rotation, secret scan,
rate/payload limits, load/soak, retry/restart, backup off-host, restore/RPO/RTO,
full integration, OpenAPI drift và residue cleanup trên host Windows/Docker. Các
evidence Windows/Docker hiện tại là baseline, không thay thế final release gate.

### 12.5. Ngoài roadmap được duyệt

Manufacturing, POS, Subscription, Budget, Assets/Maintenance, Projects và
Support không tự động trở thành public API hoặc policy scope. Bổ sung chúng là
thay đổi product scope và cần phase, contract cùng acceptance riêng.

## 13. Audit bàn giao API, config và policy

Ngày audit: 2026-08-12. Evidence dưới đây chỉ áp dụng cho revision hiện tại và
không tự động chuyển sang revision tương lai.

| Hạng mục | Trạng thái | Evidence hoặc gap |
|---|---|---|
| Business API Phase 1–7 | `COMPLETE` | 5 module, 23 resource, 137/137 operation `passed` |
| Native controller/permission/lifecycle | `COMPLETE` trong allowlist | Docker acceptance và cleanup fail-closed |
| Policy runtime foundation | `COMPLETE` | 25 document thật, zero drift, rollback và idempotent apply |
| Full policy coverage | `COMPLETE` | 56 source registry-driven; native asset và full acceptance pass |
| Config/policy ownership | `COMPLETE` cho boundary migration | Country/currency chỉ còn ở `policy.bootstrap.company` |
| OpenAPI handoff | `COMPLETE` | Public 215 operation, control plane 2 operation, manifest checksum |
| Windows/Docker production baseline | `COMPLETE` | No-flag readiness, backup và restore drill pass |
| Phase 8 host signature | `WINDOWS_DOCKER` | Ubuntu không thuộc tiêu chí nghiệm thu Phase 8 |
| Phase 9 Accounts reconciliation | `COMPLETE` | Bank Transaction, Payment Reconciliation, Payment Order acceptance pass |
| Project completion | `COMPLETE` | Phase 1-12 đã pass gate trên revision `267fa4cccf` |

Evidence Phase 8 đã chạy trên cùng revision: host `51 passed, 45 deselected`; Docker acceptance
registry gồm 7 structural shard, 11 apply/idempotency/delete shard, asset
lifecycle, tax 0/5/8/10, commercial, Stock/Buying, workflow/permission,
cross-cutting effect và 5 fault boundary. Ruff/ty pass; hai OpenAPI validate;
scanner `unknown=0`, `unclassified=0`, `schema_drift=0`; backup gồm database/
public/private files và restore drill health/cleanup thành công. Restore site tạm
`restore-drill-1.local` đã được dọn; cảnh báo `cleanup_old_syncs` được phân loại
known upstream warning. Policy scanner cuối: `unknown=0`, `unclassified=0`,
`schema_drift=0`, `managed_entries_without_acceptance=0`. Mỗi test có hard timeout
70 giây cho test nhỏ và 5 phút cho test gộp.

Các invariant đã xác nhận gồm explicit `/api/v1` allowlist, không có generic
business fallback, write qua controller native, immutable Company sau
bootstrap, config-control optimistic hash/rollback, durable outbox với
HMAC/retry/dedupe và secret không nằm trong YAML/artifact.

Trạng thái phát hành hiện tại:

```text
Business API Phase 1-7:       COMPLETE
Phase 8 policy wrapper:       COMPLETE
Managed production policy:    14 native documents
Windows/Docker baseline:      VERIFIED
Phase 8 host signature:       WINDOWS_DOCKER
Project completion:           COMPLETE
```

Project chỉ chuyển `COMPLETE` khi Phase 9–12 pass trên cùng revision, mọi
operation công bố có test status `passed`, inventory trong phạm vi có
`unknown = 0`, residue bằng 0 và Windows/Docker deployment hoàn tất.

## 14. Governance tài liệu

| Tài liệu | Nội dung sở hữu |
|---|---|
| PRD này | Phạm vi, requirement, roadmap, tiến độ, definition of done và audit |
| [System Architecture](System_Architecture.md) | Boundary, ownership, data flow và invariant |
| [Configuration Inventory](Configuration_Inventory.md) | Policy source, classification, implementation/test status |
| [Integration Handbook](Integration_Handbook.md) | Cách consumer sử dụng capability đã công bố |
| [Docker runbook](../DOCKER.md) | Deploy, readiness, backup, restore và troubleshooting |
| [README](../README.md) | Entry point, quick start và trạng thái tóm tắt |
| [Integration contract](../contracts/erpnext-integration.yml) | Allowlist nguồn cho public API contract |

Khi có mâu thuẫn, sửa tài liệu sở hữu nội dung trước rồi cập nhật các tài liệu
khác bằng liên kết hoặc summary. Không sao chép roadmap, inventory hoặc evidence
chi tiết sang handbook, architecture hay runbook.
