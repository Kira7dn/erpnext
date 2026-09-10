# Tổng kết Kiến trúc 3 Container, Production S3 Backup & Triển khai Vercel Global Portal

- **Ngày lập**: 2026-09-06
- **Trạng thái**: Hoàn tất triển khai & Kiểm chứng Zero-Drift
- **Phạm vi**: Cụm ERPNext Backend, Quy chuẩn AWS S3 Backup & Khôi phục Thảm họa, Global Portal Auth Server trên Vercel

---

## 1. Kiến trúc Runtime Tối giản Tuyệt đối (3 Container)

Hệ thống ERPNext đã được tinh giản từ mô hình 7–8 container phức tạp xuống đúng **3 container dài hạn duy nhất**, loại bỏ 100% các container one-shot bị `Exited (0)`:

```text
CONTAINER NAME        IMAGE                          STATUS                   PORTS
erpnext-backend-1     erpnext-letron-runtime:local   Up (healthy/ready)       0.0.0.0:8080->8000/tcp
erpnext-redis-1       redis:6.2-alpine               Up (ready)               6379/tcp
erpnext-db-1          mariadb:11.8                   Up (healthy)             3306/tcp
```

### Các cải tiến cốt lõi:
1. **Loại bỏ Nginx (`frontend`) & Websocket (`websocket`)**:
   - Gunicorn backend phục vụ trực tiếp cổng `8080:8000`.
   - Tất cả request `/api/...` (gồm `/api/v1` và health check) do backend xử lý trực tiếp.
2. **Gộp Redis Cache & Queue**:
   - Cả cache và queue dùng chung một container `redis:6379`.
3. **Hợp nhất Entrypoint (`docker/backend-entrypoint.sh`)**:
   - Các tác vụ khởi tạo site, migrate schema, bootstrap và đồng bộ policy được thực thi tuần tự bên trong container `backend`.
4. **Operations Profile cho Backup**:
   - Các service `backup`, `backup-verify` được đưa vào profile `operations`, chỉ kích hoạt theo lệnh (on-demand), không chạy ngầm gây lãng phí tài nguyên.

---

## 2. Quy chuẩn Sao lưu Tự động & Khắc phục Thảm họa (S3 Backup & DR)

### A. Nguyên tắc Bảo mật IAM Least Privilege & Chống Ransomware
- **IAM User tự động (`user/LeTRON-ERP`)**:
  - Chỉ cấp: `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` trên `s3://letron-erp-backups`.
  - **Tuyệt đối không cấp `s3:DeleteObject`**: Ngăn ngừa rủi ro ransomware hoặc lộ khóa xóa mất dữ liệu sao lưu.
- **IAM User Master (`user/master`)**:
  - Profile AWS CLI `letron-master` lưu độc lập tại `~/.aws/credentials`.
  - Tuyệt đối không lưu khóa Master trong `.env` hay container runtime.

### B. Vòng đời Dữ liệu S3 Lifecycle (10 năm theo Luật Kế toán)
- **0 - 30 ngày**: S3 Standard (truy xuất tức thời, độ bền 99.999999999%).
- **31 - 180 ngày**: S3 Glacier Instant Retrieval (chi phí thấp, truy xuất mili-giây).
- **181 ngày - 3.650 ngày (10 năm)**: S3 Glacier Deep Archive (chi phí siêu tiết kiệm $0.00099/GB/tháng).

### C. Lịch Sao lưu Tự động Container-Native (01:00 AM)
- Chạy thông qua Frappe Scheduler hook (`letron_api.operations.backup.scheduled_s3_backup`) lúc **01:00 AM hằng đêm** (Giờ Việt Nam).
- **100% OS-Agnostic**: Chạy độc lập bên trong container Docker, không phụ thuộc cron của host (dễ dàng chuyển đổi giữa Windows và Linux VPS).
- **Zero Local Disk Waste**: Sau khi tạo đủ 5 thành phần (Database, Config, Files VAT, Public Files, Manifest SHA-256) và tải lên S3 thành công, file cục bộ được giải phóng ngay lập tức.

### D. Diễn tập Phục hồi Định kỳ (Restore Drill)
- Lệnh: `.\docker-start.ps1 -Action backup-verify` (hoặc `./erpctl backup-verify`).
- Tự động kéo bản backup mới nhất từ S3, bung vào database tạm thời `restore-drill-1.local`, kiểm tra toàn vẹn bảng và xóa sạch sau khi hoàn tất.

---

## 3. Global Portal & OIDC Provider trên Vercel

Global Portal Auth Server (`apps/auth-server`) được triển khai lên Vercel:
- **Production URL**: `https://erp-one-henna.vercel.app`
- **OIDC Issuer**: `https://erp-one-henna.vercel.app/api/oidc`
- **Health Check Endpoint**: `https://erp-one-henna.vercel.app/api/health`
- **Database**: PostgreSQL Neon Serverless.

### Giao diện Card Backup & Disaster Recovery:
- Tích hợp trực tiếp trên trang chủ Portal ([apps/auth-server/src/components/backup-card.tsx](file:///d:/BusinessAnalyze/Letron/erp/apps/auth-server/src/components/backup-card.tsx)).
- **Tab ERP**: Liệt kê các bản backup lấy trực tiếp từ S3 với badge kiểm chứng 5/5 thành phần.
- **Bộ lọc thời gian**: Quick filters (Tất cả, Hôm nay, 7 ngày, 30 ngày) và Date Range Picker (`from` $\rightarrow$ `to`).
- **Infinite Scroll**: Phân trang theo cursor timestamp kết hợp `IntersectionObserver` mượt mà.
- **Action**: Nút *"Sao lưu tự động ngay"* và nút *"Khôi phục"* (hỗ trợ Diễn tập hoặc Phục hồi thảm họa).

---

## 4. Ma trận Biến Môi trường (Environment Matrix)

| Biến | Local Dev (`.env`) | Production / VPS (`.env.production`) | Vercel Auth Server |
| :--- | :--- | :--- | :--- |
| **`AUTH_BASE_URL`** | `http://localhost:3000` | `https://erp-one-henna.vercel.app` | `https://erp-one-henna.vercel.app` |
| **`LETRON_SSO_ISSUER`** | `http://localhost:3000/api/oidc` | `https://erp-one-henna.vercel.app/api/oidc` | *(N/A)* |
| **`LETRON_SSO_INTERNAL_ISSUER`**| `http://host.docker.internal:3000/api/oidc` | `https://erp-one-henna.vercel.app/api/oidc` | *(N/A)* |
| **`LETRON_SSO_SYNC_URL`** | `http://host.docker.internal:3000/api/internal/lark-role-snapshots` | `https://erp-one-henna.vercel.app/api/internal/lark-role-snapshots` | *(N/A)* |
| **`DATABASE_URL`** | *(Neon Postgres string)* | *(Neon Postgres string)* | *(Neon Postgres string)* |
| **`AWS_ACCESS_KEY_ID`** | `AKIA...` (user/LeTRON-ERP) | `AKIA...` (user/LeTRON-ERP) | `AKIA...` (user/LeTRON-ERP) |
| **`AWS_SECRET_ACCESS_KEY`** | *(Secret)* | *(Secret)* | *(Secret)* |
| **`S3_BUCKET_NAME`** | `letron-erp-backups` | `letron-erp-backups` | `letron-erp-backups` |

---

## 5. Quy trình Vận hành Nhanh (Runbook)

```bash
# 1. Hot reload code/config ERP cục bộ (không build lại image)
.\docker-start.ps1 -Action reload

# 2. Tạo bản sao lưu khẩn cấp lên AWS S3
.\docker-start.ps1 -Action backup

# 3. Chạy diễn tập khôi phục thử nghiệm từ AWS S3
.\docker-start.ps1 -Action backup-verify

# 4. Tra cứu danh sách bản sao lưu trên S3 (qua CLI)
uv run python scripts/restore_from_s3.py --list

# 5. Khôi phục thảm họa vào site production (Disaster Recovery)
uv run python scripts/restore_from_s3.py --latest --target-site frontend
```
