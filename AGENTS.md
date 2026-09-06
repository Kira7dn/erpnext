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

## AWS Credentials và Quản trị Master

Hệ thống phân định nghiêm ngặt hai cấp độ tài khoản AWS riêng biệt nhằm đảm bảo an toàn vận hành:

### 1. Phân định vai trò và vị trí lưu trữ

- **Tài khoản tự động hằng ngày (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`)**:
  - **Vị trí**: Lưu trong `.env` của dự án (truyền vào Docker container).
  - **IAM User**: `user/LeTRON-ERP` (Account `366950765451`, Region `ap-southeast-1`).
  - **Mục đích**: Dành cho tác vụ tự động (backup hằng ngày, CI/CD, upload file).
  - **Phân quyền**: Tuân thủ nghiêm ngặt nguyên tắc đặc quyền tối thiểu (*Least Privilege*): chỉ có `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` trên bucket `letron-erp-backups`.
  - **Ràng buộc an toàn**: Tuyệt đối **không cấp** quyền `s3:DeleteObject` cho tài khoản này nhằm phòng chống ransomware hoặc nguy cơ lộ khóa làm mất sạch các bản sao lưu trên S3. Việc dọn dẹp backup cũ do S3 Lifecycle Rules tự động thực hiện.

- **Tài khoản tối cao Master (`user/master`)**:
  - **Vị trí**: Quản lý độc lập ngoài project, lưu tại AWS CLI Profile **`letron-master`** (`~/.aws/credentials`). **Tuyệt đối không lưu khóa Master trong `.env` của dự án** để tránh rò rỉ vào container runtime hoặc git.
  - **IAM User**: `user/master` (Account `366950765451`), sở hữu policy `AdministratorAccess`.
  - **Mục đích**: Quản trị hạ tầng cấp cao và ứng cứu sự cố (*Disaster Recovery*).
  - **Khi nào được dùng**:
    - Khởi tạo, cấu hình hoặc xóa bucket S3, S3 Lifecycle Rules, bucket encryption.
    - Cấu hình hạ tầng Cloud (VPC, ECS Fargate, RDS MariaDB nếu triển khai lên cloud).
    - Tạo, thu hồi hoặc xoay vòng (*rotate*) access key cho tài khoản bot/backup.
    - Khôi phục khẩn cấp khi tài khoản thông thường bị khóa hoặc mất quyền truy cập.

### 2. Nguyên tắc an toàn và cách sử dụng tài khoản Master

- **Không nhúng vào container / script tự động**: Tuyệt đối không đưa cặp khóa Master vào `.env`, `docker-compose.yml` hoặc các cron job tự động.
- **Bảo mật tuyệt đối**: Tuyệt đối không in, log, echo hoặc commit khóa Master vào git, artifact, log file hoặc output chia sẻ.
- **Cách sử dụng qua AWS CLI**:
  - Khi cần chạy lệnh quản trị với quyền Master:
    ```bash
    aws s3 ls --profile letron-master
    aws iam list-users --profile letron-master
    ```
  - Hoặc kích hoạt tạm thời trong session làm việc của người quản trị:
    ```powershell
    $env:AWS_PROFILE = "letron-master"
    aws s3 ls
    ```

## Quy chuẩn Sao lưu Tự động (Production Backup)

- **Lịch tự động định kỳ (01:00 AM)**: Được tích hợp sẵn trong container ackend qua Frappe Scheduler hook (letron_api.backup.scheduled_s3_backup). Lịch tự động kích hoạt lúc 01:00 AM mỗi ngày theo múi giờ Asia/Ho_Chi_Minh.
- **100% OS-Agnostic**: Chạy hoàn toàn bên trong Docker container, không phụ thuộc vào Windows Task Scheduler hay crontab của máy host; khi deploy lên Ubuntu/Linux VPS lịch backup tự động duy trì mà không cần cấu hình thêm.
- **Zero Local Disk Waste**: Sau khi tạo backup, tính toán SHA-256 manifest, đẩy lên S3 letron-erp-backups và xác thực HeadObject, file local được xóa sạch ngay lập tức.
- **Lệnh On-demand thủ công**: Chỉ dùng khi dev, test hoặc chạy khẩn cấp trước khi can thiệp bảo trì hệ thống (.\docker-start.ps1 -Action backup hoặc ./erpctl backup).

## Quy chuẩn Phục hồi và Diễn tập (Production Restore & Drill)

- **Diễn tập khôi phục định kỳ (ackup-verify)**: Chạy .\docker-start.ps1 -Action backup-verify (hoặc ./erpctl backup-verify). Container tự động kéo bản backup mới nhất từ AWS S3, kiểm tra SHA-256, bung vào database diễn tập tạm thời, chạy audit 
untime_info và xóa sạch sau khi hoàn tất.
- **Phục hồi Thảm họa (Disaster Recovery)**: Khi cần khôi phục lại dữ liệu lên server mới hoặc sau sự cố:
  - Xem danh sách bản sao lưu trên S3:
    `ash
    uv run python scripts/restore_from_s3.py --list
    `
  - Khôi phục bản mới nhất vào site production:
    `ash
    uv run python scripts/restore_from_s3.py --latest --target-site frontend
    `
  - Khôi phục một timestamp cụ thể:
    `ash
    uv run python scripts/restore_from_s3.py --timestamp YYYYMMDD_HHMMSS --target-site frontend
    `
