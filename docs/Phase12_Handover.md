# Phase 12 — Final production handoff execution plan

## Mục tiêu
Phase 12 là gate production handoff cuối: không chỉ pass test chức năng, mà phải có evidence an toàn, bền vững và thao tác thực thi được trên Windows/Docker.

## 1) Chuẩn bị trước khi test
1. Xác nhận runtime sạch
```powershell
./docker-start.ps1
uv run python -m lib.api_generator check
uv run pytest tests/unit/test_api_generator.py -q
```
2. Snapshot hash revision hiện tại
- `git rev-parse --short HEAD`
- `Get-Date -Format yyyy-MM-ddTHH:mm:ss`
- Ghi lại `contracts/openapi/manifest.json` (`business.public.operations`, `control.public.operations`)

## 2) Security / secret / least-privilege
- Kiểm tra secret không nhãn resolved trong cấu hình artifact (đã có test unit) và không rò rỉ trong evidence:
```powershell
uv run pytest tests/unit/test_system_config.py::test_repository_system_config_is_secret_free -q
uv run pytest tests/unit/test_system_config.py::test_missing_secret_fails_only_when_materializing -q
```
- API-key least privilege thực địa:
  - Tạo user test (System Manager), generate key bằng `frappe.core.doctype.user.user.generate_keys`
  - Test quyền truy cập đúng theo expected (guest/limited/authorized)
  - Rotate: gọi generate_keys lần hai → key cũ invalid
  - Revoke: `enabled: 0` user hoặc disable user
  - Evidence: response status/codes từ `test_extended_api_runtime.py` hoặc run handoff mới.

## 3) Rate / payload limit
- Payload limit:
  - Verify endpoint upload theo `config/config.yaml:50` (`upload_size` mặc định `50m`).
  - Test payload vượt ngưỡng trả 413/400 (tuỳ implementation).
- Rate limit:
  - Test retry policy hiện có cho 429 trong harness (`test_integration` đã có logic) và stress ngắn với client có backoff.
  - Mục tiêu: không retry 429 như lỗi business; retry theo policy.

## 4) Retry / restart / fault boundary
- Retry policy cơ sở:
  - Unit: `uv run pytest tests/unit/test_api_runtime_harness.py -q`
  - Integration: `uv run pytest tests/integration/test_public_api_runtime.py -m integration -q`
- Restart resilience (chạy tại runtime trực tiếp):
  1. Tạo 1 request chuẩn
  2. `docker compose restart backend`
  3. Wait for health + retry request với `request_with_retry`
  4. Xác nhận không mất idempotency key cho write có retry.

## 5) Backups / restore / DR metric
- Backup verify hiện có:
```powershell
./docker-start.ps1 -Action backup
./docker-start.ps1 -Action backup-verify
```
- Ghi lại:
  - backup artifact có đầy đủ DB + files
  - thời gian chạy `backup`/`backup-verify`
  - site khôi phục sạch + cleanup sau verify
- Xác nhận RPO/RTO tại ngưỡng tổ chức internal:
  - RPO = mất mát dữ liệu theo thời gian từ lần backup gần nhất (gắn mốc start/stop)
  - RTO = thời gian khôi phục hoàn tất + runtime_health OK.

## 6) OpenAPI drift / artifact handoff
```powershell
uv run api-generator generate --output contracts/generated
uv run api-generator check
```
- Verify:
  - `manifest.json` public/control counts nhất quán với contract source
  - không có drift mới chưa được ghi chú

## 7) Load/soak (baseline)
- Chạy load script nội bộ (đề xuất dùng `pytest` marker mới hoặc script) trên 5–15 phút với endpoint ổn định:
  - read-heavy: `GET /api/method/letron_api.api.health`
  - auth-heavy: `/api/v1/stock/items?fields=["name"]&limit_page_length=1`
- Mục tiêu:
  - request_error_ratio tối thiểu
  - không tăng lỗi 5xx khi tải ổn định
  - latency p95 trong ngưỡng nội bộ

## 8) Full integration + residue
- Chạy lại 3 acceptance đã tồn tại (tối thiểu):
```powershell
uv run pytest tests/integration/test_crm_preorder.py -m integration -q --maxfail=1
uv run pytest tests/integration/test_accounts_reconciliation.py -m integration -q --maxfail=1
uv run pytest tests/integration/test_stock_traceability.py -m integration -q --maxfail=1
```
- Collect evidence cuối:
  - `not-tested = 0`, `partial = 0`, `blocked = 0`
  - `runtime_drift`, `schema_drift`, `secret_executable_leakage`, `acceptance_residue` đều `0`

## 12.4 Gate completion (dành để ký `COMPLETE`)
Phase 12 hoàn tất khi có evidence file/runbook cho đầy đủ nhóm ở trên trên cùng revision Windows/Docker, kể cả:
- API hardening có bằng chứng rotate/revoke
- security scan + payload/rate control
- restart/retry không mất khóa idempotency
- backup-off-host + restore + residue-zero
- OpenAPI drift sạch + openapi manifest cập nhật
- full integration + zero residue cuối

## Trạng thái lúc bắt đầu
- Phase 10/11 đã `COMPLETE`.
- Phase 12: `IN_PROGRESS` (thực thi theo playbook này).
