# Letron ERPNext backend workspace

Workspace này đóng gói ERPNext/Frappe thành backend cho frontend và các ứng
dụng tích hợp. ERPNext và app custom cùng nằm trong monorepo dưới `apps/`;
wrapper, config, tooling và contract nằm ở root.

## Sử dụng

Yêu cầu: Docker đang chạy và đã cài `uv`. Repository đã chứa sẵn Dockerfile, Compose,
`config/config.yaml` và `config/policy.yaml`.

Lần đầu trên Windows:

```powershell
Copy-Item .env.example .env
# Điền secret thật vào .env, sau đó chạy:
.\docker-start.ps1
```

Những lần sau, kể cả sau khi sửa YAML, chỉ chạy:

```powershell
.\docker-start.ps1
```

Trên Ubuntu:

```bash
cp .env.example .env
chmod 600 .env
chmod +x erpctl
# Điền secret thật vào .env, sau đó chạy:
./erpctl
```

Launcher tự validate, migrate, bootstrap Company, apply system config và
business policy, khởi động Docker rồi reload các service. Không truyền action.

Sau khi sẵn sàng:

```text
API base URL: http://localhost:8080
Health:       http://localhost:8080/api/method/letron_api.api.health
Business API: http://localhost:8080/api/v1/{module}/{resource}
```

Mỗi project/site là một tenant và đúng một Company. Chỉnh system/runtime trong
`config/config.yaml`, chỉnh Company và policy nghiệp vụ trong
`config/policy.yaml`, giữ secret thật trong `.env`. Không sửa managed policy
qua ERPNext Desk hoặc generic `/api/resource`.

Trạng thái cập nhật 2026-08-12: Phase 7 Accounts operational core đã hoàn thành.
Curated API có 23 resource thuộc Selling/Accounts/Buying/Contacts/Stock và đúng
137 operation; Docker acceptance đã pass toàn bộ CRUD, lifecycle, permission,
delivery staging và cleanup residue. Bank, Bank Account, Mode of Payment, Cost
Center, Journal Entry và Payment Request dùng permission/controller native;
Journal Entry chỉ sinh GL qua submit và Payment Request Outward liên kết
Purchase Invoice đã submit.

Compute có đúng hai nguồn cấu hình UTF-8 được version-control:
`config/config.yaml` là SOT cho system/runtime. `config/policy.yaml` hiện là SOT
cho bootstrap Company và 15 document native: 12 Settings cùng ba tax template
Việt Nam mặc định của ERPNext (Sales, Purchase, Item, đều 10%); chưa bao phủ
toàn bộ tax, payment, pricing, shipping, workflow và template policy của tenant.
`letron_api` chỉ export/validate/diff/apply document native; controller,
permission và Workflow native vẫn là execution engine. Secret không nằm trong
YAML mà được tham chiếu bằng `${ENV_NAME}` tới file `.env` bị Git ignore. Docker
chỉ khởi động backend sau `config-sync` và `policy-sync`; `verify` yêu cầu phạm
vi đã khai báo zero drift.

Account, GL Entry và Payment Ledger Entry không có public CRUD. Sau Phase 7
tiếp tục hoàn thiện banking/reconciliation của Accounts trước khi
mở CRM/Buying và Stock traceability. Manufacturing không thuộc roadmap public
API hiện tại.

Tài liệu chính:

- [ERP PRD](docs/ERP_PRD.md)
- [ERPNext integration contract](contracts/erpnext-integration.yml)
- [Integration handbook](docs/Integration_Handbook.md)
- [Inventory cấu hình nghiệp vụ ERPNext](docs/Configuration_Inventory.md)
- [Audit bàn giao API/config/policy](docs/ERP_PRD.md#audit-bàn-giao-api-config-và-policy)

Trạng thái bàn giao: implementation production đã đóng tám blocker P0 trên
Windows/Docker Linux, gồm rollback, artifact OpenAPI, production profile,
backup/restore và startup readiness. Clean-checkout acceptance trực tiếp trên
máy Ubuntu thật vẫn là evidence còn thiếu trước khi ký bàn giao đa nền tảng.
Evidence trên revision hiện tại: host `52 passed, 5 deselected`, Docker
integration `5 passed, 49 deselected`, 137/137 business operation `passed`,
Ruff/ty/OpenAPI validation và runtime zero-drift health đều pass.

## Cấu trúc monorepo

```text
apps/letron_api/       # app chạy bên trong Frappe/ERPNext
apps/erpnext/          # source ERPNext trong monorepo
lib/api_generator/     # inspect metadata, validate contract, sinh OpenAPI
contracts/             # integration contract YAML
docs/                  # PRD, handbook và kiến trúc
tests/                 # test cho tooling/contract
contracts/generated/    # artifact tái sinh, không chỉnh sửa trực tiếp
contracts/openapi/       # artifact public/control-plane đã version hóa để bàn giao
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
.\docker-start.ps1
```

Không sửa trực tiếp source ERPNext khi xử lý contract hoặc integration app.
Mọi thay đổi custom ERPNext cần được review như một phần của monorepo và giữ
đúng prefix `apps/erpnext/`.

`lib/api_generator` là tooling host-side, không phải API runtime. Có thể gọi
qua module hoặc console script:

```powershell
uv run python -m lib.api_generator validate
uv run python -m lib.api_generator generate
uv run python -m lib.api_generator check
uv run openapi-spec-validator contracts/openapi/public.yaml
uv run openapi-spec-validator contracts/openapi/control-plane.yaml
```

## Luồng cấu hình

```text
config/config.yaml
  -> docker-start.ps1
  -> Docker Compose
  -> Frappe common_site_config.json
  -> System Settings native
  -> config readback + drift check

config/policy.yaml
  -> policy-bootstrap tạo đúng một Company bằng controller/template native
  -> letron_api.policy export / validate / plan / apply
  -> ERPNext native configuration DocTypes
  -> policy readback + drift check

.env
  -> chỉ resolve các ${ENV_NAME}; không được API trả về hoặc ghi vào YAML
```

Có thể sửa hai YAML trực tiếp trên compute rồi chạy lại `.\docker-start.ps1`
không flag. Control-plane API nội bộ cho System Manager cũng đọc/ghi và apply
đúng hai file cố định đó:

```text
GET /api/method/letron_api.config_control.get_configuration?kind=config|policy
PUT /api/method/letron_api.config_control.put_configuration
```

PUT nhận `kind`, nội dung UTF-8 `content`, `expected_source_sha256` và
`apply_now`. Production luôn apply ngay; thay Company identity bị từ chối 409.
Nếu native apply lỗi, API phục hồi cả YAML và runtime cũ rồi xác nhận readback.
API này không phải public business contract,
vì vậy catalog vẫn đúng 23 resource/137 operation. Thay đổi cần recreate
container được trả về bằng `restart_required`; operator chạy lại
`.\docker-start.ps1` hoặc `./erpctl`, không cần truyền action.

## Tooling

```powershell
uv run python -m lib.api_generator inspect
uv run python -m lib.api_generator generate
uv run python -m lib.api_generator check
uv run python -m lib.api_generator validate
```

Catalog/module artifact được sinh tại `contracts/generated/` và bị Git ignore.
Public API cùng control-plane API dùng để bàn giao nằm tại `contracts/openapi/`;
`manifest.json` giữ checksum và `check` fail khi artifact lệch source.

## Kiểm thử

```powershell
uv run pytest
uv run ruff check staging_consumer.py lib apps/letron_api/letron_api tests
uv run ty check staging_consumer.py lib apps/letron_api/letron_api tests
.\docker-start.ps1
uv run pytest -m integration -q
```

Không sửa managed config/policy trực tiếp bằng ERPNext Desk hoặc
`/api/resource`. Thay đổi YAML, review diff rồi chạy lại launcher;
secrets/password và metadata phát sinh không nằm trong bundle.

Delivery chỉ lấy credential từ environment: `LETRON_WEBHOOK_URL`,
`LETRON_WEBHOOK_SECRET`, `LETRON_WEBHOOK_TIMEOUT_MS`, `LETRON_REALTIME_URL` và
`LETRON_REALTIME_TOKEN`. YAML chỉ chứa tham chiếu `${ENV_NAME}`; giá trị thật
nằm trong `.env` trên compute và không xuất hiện trong API/evidence.

Mọi API write phải đi qua Frappe/ERPNext để giữ permission, validation và
lifecycle của ERPNext. Không sửa trực tiếp source trong `apps/erpnext` khi xử
lý integration contract.
