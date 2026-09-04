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

## Lark SSO và Global Portal

`apps/auth-server` là Next.js OIDC Provider đứng giữa Lark và các ứng dụng
Letron. Người dùng mở Web App trong Lark, vào Global Portal rồi chọn ERP; ERP
đổi authorization code lấy identity, tạo session Frappe và chuyển tới `/desk`.

```text
Lark Web App
  -> Letron Global Portal / Auth Server (:3000)
  -> OIDC Authorization Code + PKCE
  -> ERP SSO adapter (:8080)
  -> ERPNext Desk
```

Ranh giới nguồn dữ liệu chuẩn:

| Dữ liệu | Source of truth |
|---|---|
| Danh tính, trạng thái truy cập, membership User Group | Lark |
| Liên kết người dùng | `tenant_key + union_id`; không dùng email làm identity |
| Mapping Lark Group sang role được quản lý | Environment của SSO |
| Định nghĩa Role, Role Permission, Workflow, User Permission, Company | ERPNext |

ERP tạo `System User` theo JIT ở lần đăng nhập đầu hợp lệ. Sau đăng nhập,
`auth_hooks` kiểm tra on-demand identity đang hoạt động, dùng cache 60 giây và
không chạy cron role sync. Gỡ khỏi group truy cập hoặc disable Auth User sẽ gỡ
role do Lark quản lý, disable ERP User, xóa session và từ chối request hiện tại.
Role ngoài allowlist không bị bộ đồng bộ thay đổi. Snapshot đăng nhập quá hạn
sẽ bị từ chối; lỗi làm mới kéo dài quá 10 phút sẽ stale-lock tài khoản cho tới
khi nhận snapshot hợp lệ mới.

Chạy local trong hai terminal:

```powershell
# Terminal 1: Auth Server
Set-Location apps/auth-server
npm run db:migrate
npm run dev

# Terminal 2: ERPNext
Set-Location D:\BusinessAnalyze\Letron\erp
.\docker-start.ps1 -Action up
```

Các URL local:

```text
Lark Web App / Portal: http://localhost:3000
Lark OAuth callback:   http://localhost:3000/api/auth/lark/callback
Auth health:           http://localhost:3000/api/health
ERP SSO launch:        http://localhost:8080/api/method/letron_api.sso.launch
ERP health:            http://localhost:8080/api/method/letron_api.api.health
```

`localhost` chỉ dùng được khi mở Lark Desktop trên chính máy đang chạy hai
server. Lark mobile hoặc máy khác cần URL HTTPS công khai và callback/home URL
tương ứng trong Lark Developer Console. Chi tiết cấu hình, lifecycle và
break-glass xem [Auth Server README](apps/auth-server/README.md). Thiết kế một
user thuộc nhiều group, catalog group→role và thứ tự triển khai nằm tại
[Lark SSO Role Design and Next Steps](docs/notes/Lark_SSO_Role_Design_and_Next_Steps_2026-09-05.md).
Kế hoạch đưa Driver Next.js đang dùng Amplify/Cognito JWT vào cùng luồng nằm tại
[Driver Amplify Lark SSO Action Plan](docs/notes/Driver_Amplify_Lark_SSO_Action_Plan_2026-09-05.md).

### Đăng nhập local

```text
URL:      http://localhost:8080
User:     Administrator
Password: 123456
```

> Đây là credential development local để truy cập site hiện tại. Không sử dụng
> credential này cho production; production phải dùng secret riêng và password
> mạnh hơn.

### Hot reload Docker

Khi thay đổi source, config, policy hoặc entrypoint mà không muốn build lại image:

```powershell
.\docker-start.ps1 -Action reload
```

Action này dùng image hiện có (`--no-build`), chạy lại các bước sync idempotent,
recreate các service dài hạn để nạp source mới, và không recreate `create-site`
nên không chạy lại site migration.

`reload` tự kiểm tra plan hiện tại: nếu chỉ sửa source thì chỉ restart process;
nếu phát hiện drift từ `config.yaml` hoặc `policy.yaml` thì mới chạy sync đầy đủ.

Trong môi trường dev, `up` và `restart` cũng luôn dùng image hiện có và không
build. Trước production, build tường minh bằng:

```powershell
.\docker-start.ps1 -Action build
```

Mỗi project/site là một tenant và đúng một Company. Chỉnh system/runtime trong
`config/config.yaml`, chỉnh Company và policy nghiệp vụ trong
`config/policy.yaml`, giữ secret thật trong `.env`. Không sửa managed policy
qua ERPNext Desk hoặc generic `/api/resource`.

Trạng thái sản phẩm hiện tại:

| Hạng mục | Trạng thái |
|---|---|
| Business API Phase 1–10 | `COMPLETE` — 5 module, 29 resource, 175 operation |
| Phase 10 CRM pre-order | `COMPLETE` — 4 resource, 20 operation đã `passed` |
| Phase 11 Stock traceability | `COMPLETE` — 8 resource, 40 CRUD operation contract mở; runtime status hiện tại `215 passed / 0 not-tested` |
| Phase 8 policy wrapper | `COMPLETE` — 56 source registry-driven, controller effect và rollback pass |
| Managed production policy | 14 native document thật; conditional coverage dùng disposable fixture |
| Windows/Docker baseline | `VERIFIED` — backup integrity và restore drill pass ngày 2026-08-12 |
| Phase 8 host signature | `WINDOWS_DOCKER` — Ubuntu không thuộc gate Phase 8 |
| Phase 9 Accounts reconciliation | `COMPLETE` — registry policy full node và Accounts acceptance pass trên cùng revision |
| Phase 12 Final production handoff | `COMPLETE` — 2026-08-13 chạy full gate (integration + openapi + backup + soak + restart) |
| Project completion | `COMPLETE` — Phase 12 gate đã pass trên cùng revision |

Target boundary: `config.yaml` sở hữu system/runtime; `policy.yaml` sở hữu
Company bootstrap, country, currency và business policy; `.env` giữ secret;
entity/transaction/ledger nằm trong ERPNext DB. Country/currency hiện còn mirror
được launcher lấy từ `policy.bootstrap.company`; `config.yaml` không còn mirror business jurisdiction
lâu dài.

Tài liệu chính:

- [ERP PRD](docs/ERP_PRD.md)
- [ERPNext integration contract](contracts/erpnext-integration.yml)
- [Integration handbook](docs/Integration_Handbook.md)
- [Inventory policy trong phạm vi sản phẩm](docs/Configuration_Inventory.md)
- [Audit bàn giao API/config/policy](docs/ERP_PRD.md#audit-bàn-giao-api-config-và-policy)
- [Phase 12 handoff playbook](docs/Phase12_Handover.md)

## Cấu trúc monorepo

```text
apps/letron_api/       # app chạy bên trong Frappe/ERPNext
apps/erpnext/          # source ERPNext trong monorepo
apps/auth-server/      # Global Portal và OIDC Provider dùng Lark upstream
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
vì vậy catalog vẫn đúng public contract hiện tại (37 resource, 215 operation).
Tất cả 215 operations đều đang `passed`. Thay đổi cần recreate
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
