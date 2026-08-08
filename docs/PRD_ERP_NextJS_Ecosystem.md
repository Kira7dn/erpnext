# PRD: ERPNext làm backend API cho Letron ERP

## Trạng thái triển khai

Ngày cập nhật: 2026-08-09.

Phase 1 đã hoàn thành và được kiểm tra trên Docker:

- site `frontend` chạy với Frappe, ERPNext và `letron_api`;
- MariaDB healthy, Redis hoạt động, frontend truy cập tại `localhost:8080`;
- `letron_api.api.health` trả response runtime thật;
- launcher/configurator/create-site chạy idempotent;
- seed tắt mặc định và kết thúc `Exited (0)`;
- source `erpnext` không bị chỉnh sửa.

Phase 2 đã hoàn thành phần catalog/schema/OpenAPI host-side: `workspace_api` đọc
contract, quét DocType JSON và decorator `frappe.whitelist`, sinh
`generated/catalog.json`, `generated/openapi.json` và `generated/openapi.yaml`.
Kết quả hiện tại là 813 DocType và 1.324 whitelisted method. Đây là catalog kỹ
thuật đầy đủ theo source, chưa phải subset contract đã được đóng băng cho FE.

Frappe hiện còn log cảnh báo `cleanup_old_syncs is not a valid method` khi
đồng bộ jobs. Cảnh báo này không làm site hoặc API health fail và được theo dõi
như một compatibility issue riêng.

## 1. Mục tiêu

Workspace này biến ERPNext/Frappe thành backend ERP chạy thật cho các frontend
và ứng dụng tích hợp bên ngoài.

ERPNext là hệ thống sở hữu dữ liệu, schema, permission, validation, lifecycle
và business logic. Workspace không viết lại các logic đó và không sửa source
trong thư mục `erpnext`.

Kết quả cần có:

1. Một runtime ERPNext/Frappe chạy được bằng Docker.
2. Cấu hình tập trung để khởi tạo và vận hành runtime.
3. API trong chính Frappe/ERPNext để frontend sử dụng.
4. Contract mô tả API và cách tích hợp.
5. OpenAPI sinh từ contract và metadata runtime.
6. Integration handbook có ví dụ gọi API, đồng bộ, webhook và lỗi.

## 2. Phạm vi

### Trong phạm vi

- Docker Compose, site, MariaDB, Redis và runtime settings.
- Custom Frappe app cài trong bench để bổ sung integration API khi API native
  chưa đủ.
- Frappe Document API và whitelisted methods chuẩn.
- Đọc metadata DocType, field, link, child table, permission và lifecycle.
- Catalog generic resource API và whitelisted method API.
- Contract YAML cho endpoint, schema, auth, error, webhook và realtime.
- Sinh OpenAPI 3.1 và tài liệu Markdown cho frontend/app ngoài.
- Test API thật trên site Docker.
- Webhook, realtime event, retry, request ID và idempotency ở lớp tích hợp.

### Ngoài phạm vi

- Đặc tả quy trình thanh toán, hợp đồng, kho hoặc phê duyệt riêng.
- Tạo business rule song song với ERPNext.
- BFF, API gateway hoặc backend service thứ hai.
- Thay MariaDB bằng DynamoDB.
- Sửa trực tiếp code trong `erpnext`.
- Chọn frontend framework hoặc thiết kế màn hình frontend.

## 3. Kiến trúc bắt buộc

```text
FE / external app
        |
        v
API contract + OpenAPI + Integration Handbook
        |
        v
Frappe API trong ERPNext site
  - /api/resource/{doctype}
  - /api/method/{python.dotted.path}
  - custom integration methods trong Frappe app khi cần
        |
        v
ERPNext DocType / controller / permission / hooks
        |
        v
MariaDB + Redis
```

Custom Frappe app là phần mở rộng bên trong ERPNext bench, không phải wrapper
service. Mọi ghi dữ liệu phải đi qua Frappe Document API hoặc controller chuẩn
để giữ validation, permission và lifecycle của ERPNext.

## 4. Runtime configuration

`config.yml` là desired state local và không được commit credential. Template
không chứa secret.

Config phải điều khiển tối thiểu:

- ERPNext/Frappe image và version.
- Compose project, site name và port.
- MariaDB/Redis connection.
- locale, timezone và developer settings.
- API base URL và integration mode.
- request timeout, upload limit và proxy settings.
- webhook URL, timeout, retry và delivery log.
- generated artifact directory.

`docker-start.ps1` phải validate config, render Compose, khởi tạo site và chạy
các lệnh inspect/generate/validate trong container phù hợp. Launcher không sửa
source ERPNext.

## 5. Integration contract

Contract kỹ thuật nằm tại:

```text
contracts/erpnext-integration.yml
```

Contract không mô tả nghiệp vụ cụ thể. Nó mô tả:

- ERPNext/Frappe version và runtime source.
- API base path và service identity.
- generic resource endpoint.
- whitelisted method endpoint.
- DocType metadata source.
- request/response envelope của Frappe.
- pagination, filter, ordering và field selection.
- auth/header placeholder.
- `X-Request-Id` và `X-Idempotency-Key`.
- file upload/download.
- webhook payload, retry và delivery status.
- realtime channel/event.
- OpenAPI và handbook output.

Không dùng contract để allowlist theo domain nghiệp vụ. Catalog phải phản ánh
đầy đủ API mà runtime cung cấp; frontend tự chọn endpoint cần dùng.

## 6. API catalog và tài liệu

Tooling phải chạy được bằng `.venv`/`uv` và trong Docker:

```powershell
uv run python -m workspace_api inspect
uv run python -m workspace_api generate
uv run python -m workspace_api validate
uv run python -m workspace_api handbook
```

`inspect` đọc runtime và tạo catalog gồm:

- toàn bộ generic resource API;
- toàn bộ whitelisted method có thể phát hiện;
- DocType metadata;
- field type, required, link, child table và permission metadata;
- nguồn file/controller của method khi xác định được.

`generate` tạo:

```text
generated/openapi.yaml
generated/openapi.json
docs/ERPNext_Integration_Handbook.md
```

Endpoint không có request/response type tĩnh không được âm thầm bỏ qua. Tool
phải ghi rõ schema generic hoặc runtime-derived và cảnh báo nguồn schema hạn
chế trong OpenAPI/handbook.

Handbook phải hướng dẫn được:

- base URL và headers;
- gọi resource list/detail/create/update/delete;
- gọi whitelisted method;
- metadata và permission;
- upload File;
- response/error/status code;
- request ID, idempotency và retry;
- webhook registration, payload và retry;
- pull lại record sau webhook;
- realtime event nếu runtime bật;
- ví dụ curl, Python và TypeScript.

## 7. Đồng bộ và event

REST là kênh đọc/ghi chính. Webhook chỉ thông báo thay đổi; consumer phải đọc
lại record bằng REST để lấy dữ liệu chuẩn. Pull reconciliation là cơ chế kiểm
tra định kỳ. Realtime chỉ phục vụ cập nhật tức thời cho client và không phải
source of truth.

Mọi delivery phải có request ID, trạng thái, retry có giới hạn và log đủ để
đối soát. Duplicate webhook không được tạo duplicate side effect.

SSO/JWT production chưa thuộc phase đầu. Tài liệu chỉ dành chỗ cho auth header
và identity context để sau này thay cơ chế xác thực mà không đổi contract API.

## 8. Lộ trình thực hiện

### Phase 1 - Runtime và Frappe app — Hoàn thành

- Hoàn thiện Docker/site startup.
- Tạo skeleton custom Frappe app ở root workspace.
- Cài app vào bench mà không sửa `erpnext`.
- Kiểm tra API native, metadata và permission trên site thật.
- Health endpoint đã kiểm tra: `GET /api/method/letron_api.api.health`.

### Phase 2 - Catalog và contract — Phần catalog hoàn thành

- Định nghĩa `erpnext-integration.yml`.
- `workspace_api` quét source DocType và whitelisted methods.
- Catalog DocType, generic API và whitelisted methods đã được sinh.
- Validate contract với metadata runtime.

### Phase 3 - OpenAPI và handbook — Đang thực hiện

- OpenAPI 3.1 JSON/YAML đã được sinh từ catalog và contract.
- Sinh handbook có ví dụ gọi thật.
- Mô tả error, upload, webhook, realtime, retry và reconciliation.

### Phase 4 - Verification — Chưa bắt đầu

- Chạy contract test trên Docker.
- Kiểm tra CRUD, RPC, permission và lỗi.
- Kiểm tra webhook duplicate/retry.
- Kiểm tra artifact không chứa credential.
- Kiểm tra source `erpnext` không thay đổi.

## 9. Tiêu chí nghiệm thu

- FE có thể dùng handbook để gọi ERPNext mà không cần đọc source ERPNext.
- OpenAPI parse được bằng validator OpenAPI 3.1.
- Catalog phản ánh generic API, whitelisted method và DocType metadata runtime.
- Request/response/error có ví dụ thực tế.
- API write vẫn chạy qua permission/controller/lifecycle của ERPNext.
- Webhook và pull reconciliation có hành vi xác định khi retry.
- Runtime khởi động lại được bằng config.
- Không có tài liệu nghiệp vụ trong workspace technical này.
- Không có thay đổi trong `erpnext` submodule.
