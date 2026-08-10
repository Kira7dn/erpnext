# Letron ERPNext backend workspace

Workspace này đóng gói ERPNext/Frappe thành backend cho frontend và các ứng
dụng tích hợp. ERPNext và app custom cùng nằm trong monorepo dưới `apps/`;
wrapper, config, tooling và contract nằm ở root.

Trạng thái hiện tại: [DONE] Phase 1 đã chạy được trên Docker. Site `frontend` có
`frappe`, `erpnext`, `letron_api`; frontend ở `http://localhost:8080`. Phase
2: [DONE] catalog và OpenAPI generator host-side; Phase 3 [DONE] với handbook,
schema, error contract và runtime verification nền tảng.

Tài liệu chính:

- [PRD kỹ thuật](docs/PRD_ERP_NextJS_Ecosystem.md)
- [ERPNext integration contract](contracts/erpnext-integration.yml)
- [Integration handbook](docs/ERPNext_Integration_Handbook.md) (sinh sau khi runtime chạy)
- [ERPNext monorepo sync](docs/ERPNext_Monorepo.md)

## Cấu trúc monorepo

```text
apps/letron_api/       # app chạy bên trong Frappe/ERPNext
apps/erpnext/          # source ERPNext trong monorepo
lib/api_generator/     # inspect metadata, validate contract, sinh OpenAPI
contracts/             # integration contract YAML
docs/                  # PRD, handbook và kiến trúc
tests/                 # test cho tooling/contract
contracts/generated/    # artifact tái sinh, không chỉnh sửa trực tiếp
```

`lib/api_generator` là tooling host-side, không phải API runtime. Có thể gọi
qua module hoặc console script:

```powershell
uv run python -m lib.api_generator validate
uv run api-generator validate
```

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
uv run python -m lib.api_generator inspect
uv run python -m lib.api_generator generate
uv run python -m lib.api_generator validate
```

Artifact được sinh tại `contracts/generated/` và bị Git ignore vì có thể tái sinh từ
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
