# ERPNext Integration Handbook

## Trạng thái runtime

Đã kiểm tra trên Docker ngày 2026-08-09:

```text
site: frontend
apps: frappe, erpnext, letron_api
frontend: http://localhost:8080
```

Health endpoint:

```text
GET /api/method/letron_api.api.health
```

Response thực tế:

```json
{
  "message": {
    "ok": true,
    "app": "letron_api",
    "site": "frontend",
    "frappe_version": "16.30.0",
    "installed_apps": ["frappe", "erpnext", "letron_api"]
  }
}
```

Catalog/OpenAPI host-side đã sinh bằng `uv run python -m workspace_api generate`:

- `generated/catalog.json`: 813 DocType, 1.324 whitelisted method.
- `generated/openapi.yaml` và `generated/openapi.json`: generic Frappe resource
  API, metadata endpoint và các whitelisted method phát hiện từ source.

Các file `generated/` bị ignore vì là artifact có thể tái sinh; không chỉnh sửa
thủ công.

Frappe có thể ghi cảnh báo job DuckDB `cleanup_old_syncs` không tồn tại trong
quá trình migrate. Cảnh báo này không chặn API health hoặc startup hiện tại.

Tài liệu này là đầu ra tích hợp cho frontend và ứng dụng bên ngoài. Nội dung
đầy đủ sẽ được sinh từ runtime metadata, contract và API catalog bằng tooling
được mô tả trong [PRD](PRD_ERP_NextJS_Ecosystem.md).

## Runtime API

Các nhóm API cần catalog:

- `GET/POST/PUT/DELETE /api/resource/{doctype}`
- `GET/POST /api/method/{python.dotted.path}`
- DocType metadata và permission metadata
- File upload/download
- webhook và realtime event khi được bật trong runtime

## Quy ước tích hợp

- Gửi `X-Request-Id` cho mỗi request.
- Dùng `X-Idempotency-Key` cho request có side effect.
- Kiểm tra `message`, lỗi HTTP và lỗi Frappe trong response.
- Sau webhook, đọc lại record bằng REST; realtime không phải source of truth.
- Consumer phải retry có giới hạn và có reconciliation bằng pull.

## Generated API reference

OpenAPI 3.1 và ví dụ request/response sẽ được sinh tại:

```text
generated/openapi.yaml
generated/openapi.json
```

Không ghi credential hoặc token thật vào handbook hay artifact sinh ra.

## Sinh catalog và OpenAPI

```powershell
uv run python -m workspace_api validate
uv run python -m workspace_api inspect
uv run python -m workspace_api generate
uv run pytest
```

Generator chạy trên source checkout và không import Frappe trên host. Test
nghiệp vụ/runtime của ERPNext phải chạy trong Docker bằng `bench --site frontend
run-tests` hoặc gọi HTTP qua frontend.
