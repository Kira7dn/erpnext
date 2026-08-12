# Bàn giao Phase 9 — Accounts reconciliation

Ngày cập nhật: 2026-08-13  
Môi trường: Windows/Docker, Compose chính `erpnext`

## Trạng thái

Phase 9 hiện **COMPLETE**.

Đã có evidence pass:

| Nhóm | Test | Kết quả |
|---|---|---:|
| Public API | `test_public_contract_and_lifecycle` | PASS — 53.59s |
| Policy runtime | `42/42` node trong `tests/integration/test_policy_runtime.py` | PASS |
| Accounts | Endpoint contract | PASS — 9.04s |
| Accounts | Real-user permission | PASS — 8.09s |
| Accounts | Bank Transaction readback/reconcile | PASS — 9.76s |
| Accounts | Registry-driven compliance (`test_extended_api_runtime`) | PASS |
| Unit | Toàn bộ `tests/unit` | PASS — 51 tests |

## Cấu trúc test

```text
tests/
  unit/
  integration/
    api_runtime_harness.py
    test_public_api_runtime.py
    test_extended_api_runtime.py
    test_policy_runtime.py
    test_accounts_reconciliation.py
```

Test node được chạy riêng, giới hạn 70 giây/node. Full-suite không phải điều
kiện bắt buộc để ký Phase 9; mọi node integration trong registry vẫn phải pass
riêng lẻ, không timeout, không teardown error và không residue.

## Runtime gate hiện tại

- Compose chính hợp lệ qua `docker-start.ps1 -Action config`.
- Runtime health đã khôi phục `ok=true`.
- Company count: `1`.
- Policy drift: `0`.
- Policy sync: `applied=0`, `drift_count=0`.
- Acceptance overlay và event-consumer container đã được loại bỏ.
- Không xóa DB, volume hoặc dữ liệu tenant.

## Việc còn lại để ký COMPLETE

Tất cả gate đã pass tại revision chạy nghiệm thu cuối:

1. Extended business flow (`LETRON_DELIVERY_ENABLED=false`), pass.
2. Full registry policy nodes trong `test_policy_runtime.py`, pass.
3. Runtime snapshot/runtime drift/round-trip/cleanup cuối cùng đều `0`/pass.
4. OpenAPI manifest đã validate (`lib.api_generator validate`) trên cùng revision.
5. `Phase 9` đã được đánh dấu `COMPLETE` trong README/PRD/handbook.

## Quy tắc vận hành

- Chỉ dùng `docker-compose.yml` và `docker-start.ps1`.
- Không tạo Compose project thứ hai.
- Không chạy full-suite trước khi các node riêng lẻ pass.
- Không đưa Bank Transaction, Payment Entry, Payment Order hoặc ledger vào
  `config/policy.yaml`; đây là runtime entity.
