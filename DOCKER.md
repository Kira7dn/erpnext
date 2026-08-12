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

Compose chỉ dùng stack ERPNext chính; không có acceptance overlay hay staging
event consumer. Production delivery chỉ chạy khi `delivery.enabled: true`.
Backup dùng `bench backup` native, mặc định mỗi 24
giờ, retention 14 ngày. `backup-verify` restore vào site/database dùng một lần
rồi tự cleanup, không ghi đè site `frontend`.

## Readiness và release evidence

Launcher chỉ trả exit code `0` sau khi config/policy validate, bootstrap/sync
hoàn tất, runtime zero drift, `restart_required: false` và HTTP health pass.
`backup-verify` phải restore vào site/database dùng một lần rồi cleanup; không
được ghi đè site production.

Kết quả chạy cụ thể, trạng thái Ubuntu và quyết định bàn giao chỉ được ghi tại
[audit trong PRD](docs/ERP_PRD.md#audit-bàn-giao-api-config-và-policy). Runbook
này chỉ định nghĩa cách vận hành, không phải SOT tiến độ sản phẩm.

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
