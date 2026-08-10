# Letron ERPNext backend workspace

Workspace này đóng gói ERPNext/Frappe thành backend cho frontend và các ứng
dụng tích hợp. ERPNext và app custom cùng nằm trong monorepo dưới `apps/`;
wrapper, config, tooling và contract nằm ở root.

Trạng thái cập nhật 2026-08-11: runtime Docker, catalog, metadata, OpenAPI
curated và handbook nền tảng đã hoàn thành. Curated API hiện có 11 resource
Selling/Accounts/Buying/Stock cùng durable event outbox. Core Docker acceptance
đã pass; delivery acceptance vẫn `blocked external` cho đến khi cấu hình đủ
staging webhook/realtime consumer.

Tài liệu chính:

- [ERP PRD](docs/ERP_PRD.md)
- [ERPNext integration contract](contracts/erpnext-integration.yml)
- [Integration handbook](docs/ERPNext_Integration_Handbook.md) (sinh sau khi runtime chạy)

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

## ERPNext trong monorepo

ERPNext được quản lý trực tiếp tại `apps/erpnext/` bằng Git subtree. Workspace
chỉ có một repository chính; remote `erpnext-fork` là nguồn đồng bộ tùy chọn,
không phải một checkout thứ hai.

Kiểm tra hoặc thêm remote fork:

```powershell
git remote -v
git remote add erpnext-fork https://github.com/Kira7dn/erpnext.git
git fetch erpnext-fork version-16
```

Nếu remote đã tồn tại thì không chạy lại `git remote add`.

Đồng bộ phiên bản ERPNext:

```powershell
git fetch erpnext-fork version-16
git subtree pull --prefix=apps/erpnext erpnext-fork version-16
uv run python -m lib.api_generator generate
uv run pytest -q
.\docker-start.ps1 -Action verify
```

Không sửa trực tiếp source ERPNext khi xử lý contract hoặc integration app.
Mọi thay đổi custom ERPNext cần được review như một phần của monorepo và giữ
đúng prefix `apps/erpnext/`.

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
uv run ty check lib apps/letron_api/letron_api tests
docker compose config
```

Delivery chỉ lấy credential từ environment: `LETRON_WEBHOOK_URL`,
`LETRON_WEBHOOK_SECRET`, `LETRON_WEBHOOK_TIMEOUT_MS`, `LETRON_REALTIME_URL` và
`LETRON_REALTIME_TOKEN`. Không ghi các giá trị này vào `config.yml` hay evidence.

Mọi API write phải đi qua Frappe/ERPNext để giữ permission, validation và
lifecycle của ERPNext. Không sửa trực tiếp source trong `apps/erpnext` khi xử
lý integration contract.
