# ERPNext backend bằng Docker

Runtime hiện đã được kiểm tra: `frontend`, backend, workers và frontend đều
chạy; `configurator`, `create-site` và seed là các job một lần nên kết thúc với
`Exited (0)` khi thành công. Seed đang tắt mặc định.

Docker là runtime duy nhất của ERPNext trong workspace này. Windows host chỉ
cần Docker, uv và Node tooling; không cần cài MariaDB hoặc Redis native.

## Cấu hình

```text
config.yml -> docker-start.ps1 -> Compose environment
           -> common_site_config.json
           -> site_config.json
           -> ERPNext/Frappe API
```

`config.yml` chứa credential local và được Git ignore. Tạo từ template:

```powershell
Copy-Item config.template.yml config.yml
.\docker-start.ps1 -Action config
.\docker-start.ps1 -Action up
```

`common_site_config.json` chứa cấu hình dùng chung cho bench. `site_config.json`
chứa database credential và encryption key của site; launcher không ghi đè
credential đã sinh.

## Launcher

```powershell
.\docker-start.ps1 -Action config
.\docker-start.ps1 -Action up
.\docker-start.ps1 -Action ps
.\docker-start.ps1 -Action logs -FollowLogs
.\docker-start.ps1 -Action restart
.\docker-start.ps1 -Action down
```

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
uv run python -m workspace_api inspect
uv run python -m workspace_api generate
```

OpenAPI và handbook là tài liệu mô tả API thật của ERPNext, không phải một
backend thay thế ERPNext.

## Reset local

Lệnh sau xóa volume local và dữ liệu local:

```powershell
docker compose down -v
.\docker-start.ps1 -Action up
```
