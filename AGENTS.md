# Hướng dẫn vận hành Letron ERP

## Encoding

- Khi đọc hoặc xử lý file có tiếng Việt, luôn đọc nội dung bằng UTF-8.
- Không dùng encoding mặc định của PowerShell cho file tiếng Việt.

## Docker hot reload

Khi thay đổi source code, `config.yaml`, `policy.yaml` hoặc entrypoint Docker,
nhưng không muốn build lại image, dùng:

```powershell
.\docker-start.ps1 -Action reload
```

`reload` sẽ:

- dùng image hiện có với `--no-build`;
- chạy lại `config-sync`, `policy-bootstrap` và `policy-sync`;
- recreate các service dài hạn để nạp source/config mới;
- không recreate `create-site`;
- không chạy lại site migration;
- kiểm tra config/policy drift, Setup Wizard completion, landing route `/desk`
  và HTTP readiness.

Không dùng raw `docker compose up` để thay thế launcher, vì launcher chịu trách
nhiệm nạp environment từ `config/config.yaml`, validate bundle và chạy readiness.

## Phân biệt các action

- `.\docker-start.ps1 -Action reload`: hot reload hằng ngày, không build image.
- `.\docker-start.ps1 -Action build`: build image một cách tường minh trước
  production; không dùng action này trong vòng lặp phát triển hằng ngày.
- `.\docker-start.ps1 -Action up`: khởi động theo flow đầy đủ của launcher.
- `.\docker-start.ps1 -Action restart`: dừng và khởi động lại toàn bộ stack;
  chỉ dùng khi cần restart toàn hệ thống.
- `.\docker-start.ps1 -Action verify`: kiểm tra health và zero drift.
- `.\docker-start.ps1 -Action config`: chỉ validate Compose, config và policy.

Sau khi `reload` hoặc thay đổi landing route, đóng tab ERPNext cũ và mở lại
`/login` để browser nhận lại `frappe.boot` và session defaults mới.

## Lark SSO và Auth Server

- `apps/auth-server` là Global Portal/OIDC Provider; có thể phát triển và kiểm
  tra độc lập bằng npm, không cần chạy ERPNext hoặc Docker cho thay đổi chỉ ở
  Auth Server.
- Chỉ chạy/reload Docker khi cần nạp hoặc kiểm chứng adapter ERP trong
  `apps/letron_api/letron_api/sso*.py`, hooks, DocType hoặc cấu hình Frappe.
- Trước khi sửa Next.js, đọc `apps/auth-server/AGENTS.md` và tài liệu đúng phiên
  bản trong `apps/auth-server/node_modules/next/dist/docs/`.
- Không in nội dung `.env`, token, app secret, OIDC client secret, cookie key,
  JWKS private key hoặc database credential. Không dùng `bench show-config`
  trong output chia sẻ vì lệnh này có thể hiện secret của site.
- Secret thật và Lark group ID thật chỉ nằm trong `.env` bị Git ignore; source,
  README và `.env.example` chỉ dùng placeholder.

### Invariant identity và quyền

- Stable identity bắt buộc là `lark + tenant_key + union_id`; không fallback
  sang `open_id` và không tự liên kết tài khoản chỉ vì trùng email.
- Lark là SOT cho trạng thái truy cập và membership User Group. ERPNext là SOT
  cho định nghĩa Role, Role Permission, Workflow, User Permission và Company.
- `ERP - Access` là required access group. Một user có thể thuộc nhiều group
  nghiệp vụ; desired ERP roles là phép hợp của mọi group mapping đang khớp.
- Group phải biểu diễn chức năng công việc, không tạo theo từng cá nhân hoặc
  sao chép toàn bộ role lẻ của ERPNext. Manager group có thể ánh xạ thành bundle
  gồm cả role User và Manager tương ứng.
- Global Portal chỉ render ứng dụng/tính năng khớp role suy ra từ cùng group-role
  mapping. UI visibility không phải authorization boundary; ERPNext vẫn phải
  kiểm tra permission trên mọi request.
- Bộ đồng bộ chỉ được thêm/xóa role thuộc
  `LETRON_SSO_LARK_MANAGED_ROLES`; không sửa role ngoài allowlist.
- Không cho mapping quản lý `Administrator`, `All`, `Guest` hoặc
  `System Manager`.
- Gỡ required access group hoặc disable Auth User phải disable ERP User, gỡ
  managed roles và xóa session. Local admin block không được sync tự mở lại.
- Break-glass phải là operator command không public, có reason, TTL bị giới hạn
  và không được vượt access removal/local block.

### On-demand role sync, migration và kiểm chứng

- Role sync không dùng cron. `auth_hooks` kiểm tra identity đang gửi request sau
  mỗi `LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS`; giữ distributed lock để các
  request song song không gọi Lark trùng nhau.
- Không dùng `bench execute` hoặc reconcile thủ công làm bằng chứng on-demand.
  Phải chờ cache hết hạn, gửi request ERP đã xác thực và xác nhận
  `last_sync_at` tự cập nhật.
- `System Settings.enable_scheduler` vẫn do `config/config.yaml` quản lý vì các
  job ERP khác; không dùng trạng thái scheduler làm bằng chứng role sync.
- Khi deploy phiên bản loại bỏ cron cũ, phải chạy migrate/sync scheduled jobs
  một lần và xác nhận không còn method `letron_api.sso.reconcile_lark_roles`.
- `reload` không chạy migration. Khi thêm hoặc đổi DocType/schema Frappe, dùng
  flow `-Action up`/migration phù hợp trước, sau đó mới dùng `reload` hằng ngày.
- Sau thay đổi Auth Server chạy `npm run check`. Sau thay đổi ERP SSO chạy unit
  test liên quan, runtime acceptance rollback-only, `-Action reload` và
  `-Action verify`.
- Phân biệt backend verification với acceptance tương tác: redirect/health và
  on-demand refresh xanh chưa thay thế lần người dùng mở App thật trong Lark và
  vào ERP Desk.
