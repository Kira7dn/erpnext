# Letron ERPNext backend workspace

Workspace này đóng gói ERPNext/Frappe thành backend cho frontend và các ứng
dụng tích hợp. `erpnext/` là source checkout riêng; wrapper, config, tooling
và contract nằm ở root.

Trạng thái hiện tại: Phase 1 đã chạy được trên Docker. Site `frontend` có
`frappe`, `erpnext`, `letron_api`; frontend ở `http://localhost:8080`. Phase
2 đã có catalog và OpenAPI generator host-side; Phase 3 còn review subset
contract và kiểm thử runtime các endpoint được chọn.

Tài liệu chính:

- [PRD kỹ thuật](docs/PRD_ERP_NextJS_Ecosystem.md)
- [ERPNext integration contract](contracts/erpnext-integration.yml)
- [Integration handbook](docs/ERPNext_Integration_Handbook.md) (sinh sau khi runtime chạy)

## Chạy runtime

```powershell
Copy-Item config.template.yml config.yml
# sửa credential local trong config.yml
.\docker-start.ps1 -Action config
.\docker-start.ps1 -Action up
```

MariaDB và Redis chạy trong Docker; không cần cài native trên Windows.

## Luồng cấu hình

```text
config.yml
  -> docker-start.ps1
  -> Docker Compose
  -> Frappe common_site_config.json
  -> site_config.json
  -> ERPNext API runtime
```

## Tooling

```powershell
uv run python -m workspace_api inspect
uv run python -m workspace_api generate
uv run python -m workspace_api validate
uv run python -m workspace_api generate
```

Artifact được sinh tại `generated/` và bị Git ignore vì có thể tái sinh từ
source và contract.

## Kiểm thử

```powershell
uv run pytest
uv run ruff check .
uv run ty check bootstrap-seed.py
docker compose config
```

Mọi API write phải đi qua Frappe/ERPNext để giữ permission, validation và
lifecycle của ERPNext. Không sửa trực tiếp source trong `erpnext`.
