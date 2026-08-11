# ERPNext backend bằng Docker

Runtime hiện đã được kiểm tra: frontend, backend và workers đều chạy;
`configurator`, `create-site`, `policy-bootstrap`, `config-sync` và
`policy-sync` là các job một lần nên kết thúc với `Exited (0)` khi thành công.

Docker là runtime duy nhất của ERPNext trong workspace này. Host chỉ cần Docker
và `uv`; không cần cài MariaDB, Redis hoặc Node runtime native để khởi động ERP.

## Cấu hình

```text
config/config.yaml -> launcher -> Compose/common_site_config/System Settings
config/policy.yaml -> policy-sync -> ERPNext native policy DocTypes
.env               -> resolve ${ENV_NAME} secret references only
```

Hai YAML đã có sẵn sau khi clone và là SOT trên compute. `.env` chứa secret thật,
được Git ignore và chỉ cần tạo một lần:

```powershell
Copy-Item .env.example .env
# thay các giá trị change-me
.\docker-start.ps1
```

`common_site_config.json` chứa cấu hình dùng chung cho bench. `site_config.json`
chứa database credential và encryption key của site; launcher không ghi đè
credential đã sinh.

Ubuntu dùng cùng nguồn cấu hình:

```bash
cp .env.example .env && chmod 600 .env
chmod +x erpctl
./erpctl
```

## Launcher

Lệnh duy nhất để triển khai hoặc reconcile lại runtime là:

```powershell
.\docker-start.ps1
```

Launcher tự chạy toàn bộ dependency chain và reload service. Không cần chọn
action; lệnh chỉ trả exit code 0 sau khi config/policy zero drift và HTTP health
sẵn sàng. Các action sau chỉ là công cụ bảo trì/chẩn đoán dành cho operator:

```powershell
.\docker-start.ps1 -Action config-validate
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action config
.\docker-start.ps1 -Action config-plan
.\docker-start.ps1 -Action config-apply
.\docker-start.ps1 -Action policy-export
.\docker-start.ps1 -Action policy-plan
.\docker-start.ps1 -Action policy-apply
.\docker-start.ps1 -Action bootstrap
.\docker-start.ps1 -Action ps
.\docker-start.ps1 -Action logs -FollowLogs
.\docker-start.ps1 -Action restart
.\docker-start.ps1 -Action backup
.\docker-start.ps1 -Action backup-verify
.\docker-start.ps1 -Action down
```

Hai validate action chỉ đọc đúng YAML tương ứng và không cần resolve `.env`.
Mọi action runtime luôn dùng hai path cố định trong `config/`; launcher không
nhận path override. `workers.short_replicas` mặc định là `2` để delivery queue
đáp ứng hard deadline mà không phải chia sẻ với default queue.

Production Compose không chạy staging event consumer. Acceptance dùng riêng
`docker-compose.acceptance.yml`; production delivery chỉ chạy khi
`delivery.enabled: true`. Backup dùng `bench backup` native, mặc định mỗi 24
giờ, retention 14 ngày. `backup-verify` restore vào site/database dùng một lần
rồi tự cleanup, không ghi đè site `frontend`.

## Evidence runtime hiện tại

Cập nhật 2026-08-12 trên revision bàn giao hiện tại:

- `docker-start.ps1` không flag đã hoàn tất production readiness;
- config và policy cùng `in-sync`, `drift_count: 0`, đúng một Company
  `Letron Việt Nam`;
- HTTP health pass và `restart_required: false`;
- Docker integration đạt `5 passed, 49 deselected`; cleanup fail-closed không
  còn fixture, File, outbox, GL/Payment/Stock Ledger hoặc consumer event của run;
- backup gồm config, database, public/private files và restore drill đã pass;
- production profile không chạy staging event consumer.

`erpctl` đã được kiểm tra cú pháp Bash trong Linux container. Việc chạy toàn bộ
clean-checkout acceptance trên máy Ubuntu thật vẫn là evidence bắt buộc trước
khi ký bàn giao đa nền tảng; tài liệu không coi kiểm tra cú pháp là Ubuntu
production acceptance.

## Kiểm tra API runtime

Sau khi site chạy:

```powershell
docker compose exec backend bench --site frontend show-config
docker compose exec backend bench --site frontend list-apps
docker compose exec backend bench --site frontend console
```

Tool integration đọc metadata và API catalog trong container có Frappe runtime:

```powershell
docker compose exec backend bench --site frontend execute frappe.get_meta --args "['DocType']"
uv run python -m lib.api_generator inspect
uv run python -m lib.api_generator generate
```

OpenAPI và handbook là tài liệu mô tả API thật của ERPNext, không phải một
backend thay thế ERPNext.

## Reset local

Lệnh sau xóa volume local và dữ liệu local:

```powershell
docker compose down -v
.\docker-start.ps1
```
