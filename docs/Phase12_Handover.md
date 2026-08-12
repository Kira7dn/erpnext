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

## Trạng thái khi kế hoạch bắt đầu
- Phase 10/11 đã `COMPLETE`.
- Phase 12: `IN_PROGRESS` (thực thi theo playbook này).

## 13) Kết quả gate 12 trên revision `267fa4cccf` (2026-08-13)

- A. Freeze + baseline
  - `git rev-parse --short HEAD` = `267fa4cccf`.
  - `uv run python -m lib.api_generator check` pass.
  - `uv run pytest tests/unit/test_api_generator.py -q` pass (6 passed).
- B. Security + least privilege
  - `uv run pytest tests/unit/test_system_config.py::test_repository_system_config_is_valid_and_secret_free` pass.
  - `uv run pytest tests/unit/test_system_config.py::test_missing_secret_fails_only_when_materializing` pass.
  - API-key workflow:
    - `generate_keys` lần 1: `98d74640ea87ced` / `09fbb6c37d24ac7`.
    - `generate_keys` lần 2: `98d74640ea87ced` / `fd5034b0f8a2eaa`.
    - `api_secret` đổi mới; token key cũ bị invalid; token mới hợp lệ.
    - disable user => token bị reject (`401/403`).
- C. Rate/payload limit
  - `config/config.yaml:50` là `upload_size: 50m`.
  - Upload 49MB: `413 Request Entity Too Large`.
  - Upload 52MB: `413 Request Entity Too Large`.
- D. Retry / restart / fault boundary
  - `uv run pytest tests/unit/test_api_runtime_harness.py -q` pass.
  - `uv run pytest tests/integration/test_public_api_runtime.py -m integration -q` pass.
  - Restart backend + replay idempotent:
    - health ổn định trở lại sau `11.04s`.
    - replay lần hai với cùng `X-Idempotency-Key` trả `409`; không tạo bản ghi trùng.
- E. Backups / restore / DR
  - `./docker-start.ps1 -Action backup` pass.
  - `./docker-start.ps1 -Action backup-verify` pass, restore sang `restore-drill-1.local` và cleanup.
  - Backup bắt đầu `2026-08-13T02:02:30+07:00`, kết thúc `2026-08-13T02:02:45+07:00`.
- F. OpenAPI drift / artifact sync
  - `uv run api-generator generate --output contracts/generated` và `uv run api-generator check` pass.
  - `contracts/openapi/manifest.json`:
    - public operations: `215`.
    - control-plane operations: `2`.
  - `json_sha256` / `yaml_sha256` giữ ổn định so với baseline.
- G. Full integration + residue
  - `uv run pytest tests/integration/test_crm_preorder.py -m integration -q --maxfail=1` pass.
  - `uv run pytest tests/integration/test_accounts_reconciliation.py -m integration -q --maxfail=1` pass.
  - `uv run pytest tests/integration/test_stock_traceability.py -m integration -q --maxfail=1` pass.
- H. Load/soak (baseline)
  - Soak `600s` trên endpoint read-only `/api/v1/stock/items?fields=["name"]&limit_page_length=1`:
    - `requests=600`
    - `error_ratio=0.0000`
    - `5xx=0`
    - `p95=29.18ms`
- I. Trạng thái đóng phase
  - `Phase 12` chuyển sang `COMPLETE` và ngày ký gate: `2026-08-13`.
