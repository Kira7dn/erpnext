# Audit tuân thủ Thông tư 99/2025/TT-BTC — 2026-09-14

## Kết luận điều hành

Trạng thái code/runtime backend hiện tại là **READY cho việc lập báo cáo thật
trong scope đã cấu hình**. Gateway HTTP thật đã xác nhận Auth entitlement và
route policy, nhưng ERP vẫn fail closed vì site `frontend` chưa có bản ghi
`Letron SSO Identity` hoạt động cho test Global Admin; đây là SSO provisioning
gate, không phải lý do bypass Auth:
bộ báo cáo năm
`B01-DN`, `B02-DN`, `B03-DN`, `B09-DN` đã có policy, native adapter, validation,
package và acceptance trên Docker.

Các việc dưới đây là operational release gate của từng kỳ, không phải blocker
cho readiness của hệ thống:

1. nạp giao dịch/chứng từ thật của từng pháp nhân trong kỳ áp dụng;
2. đối chiếu B01/B02/B03/B09 với sổ cái, sổ chi tiết và chứng từ nguồn;
3. accounting owner/kế toán trưởng duyệt số liệu trước khi phát hành.

Nếu báo cáo hợp nhất có NCI, thuế thu nhập hoãn lại hoặc quy đổi ngoại tệ,
phải mở thêm phạm vi triển khai tương ứng; các capability này hiện được đánh
dấu ngoài phạm vi của package hợp nhất hiện tại.

## Căn cứ và phạm vi

- Căn cứ pháp lý: [Công báo Thông tư 99/2025/TT-BTC](https://congbao.chinhphu.vn/van-ban/thong-tu-so-99-2025-tt-btc-46529.htm), ban hành ngày 27/10/2025 và có hiệu lực từ 01/01/2026.
- Phạm vi code/config: COA VAS, Cost Center, BCTC năm, Cash Flow phương pháp
  gián tiếp, B09 có nguồn, native Journal Entry/GL và package hợp nhất.
- Phạm vi runtime: site `frontend`, công ty báo cáo `Letron Holding`, 7 công
  ty giao dịch (`Letron Holding`, `LeSC`, `LeSM`, `LeDB`, `LeSE`, `LeSB`,
  `LeGM`), tiền tệ sample `VND`.
- Không kết luận thay cho kế toán về chính sách kế toán cụ thể, số liệu thuế,
  giá trị hợp lý, tính đầy đủ chứng từ hoặc việc doanh nghiệp có thuộc phạm vi
  lập báo cáo hợp nhất/giữa niên độ hay không.

## Ma trận kiểm tra

| Hạng mục | Bằng chứng hiện tại | Kết quả | Nhận định |
|---|---|---:|---|
| Policy TT99 | `config/policy.yaml`, version 3, schema 3, policy hash `b5ad399a5b6e7768cb0b988ca9213a0e854a7fa2748ddc41996b40f89041019d` | Pass | Policy validator trả `ok=true`, 90 managed documents, `unclassified_sources=0`, `managed_entries_without_acceptance=0`, `schema_drift=0` |
| Bộ mẫu BCTC năm | `shared.coa_template.bctc_mapping.statutory_forms` | Pass | Đủ và chỉ gồm B01-DN, B02-DN, B03-DN, B09-DN; B09 có 10 note lines bắt buộc |
| COA/Account TT99 | Shared COA policy và native Account tree | Pass | Catalog 184 mã TT99, quan hệ cha-con được validate; runtime bootstrap đã materialize cho 8 Company |
| B01-DN | Native GL, opening/closing balance, due-date maturity và detail source | Conditional | Adapter/guard có; cần đối chiếu số liệu thật và phân loại ngắn/dài hạn theo hồ sơ thực tế |
| B02-DN | Native P&L, comparative period, Shareholder cho basic EPS | Conditional | Adapter/guard có; diluted EPS chỉ `not_applicable` khi không có native source, cần accounting owner xác nhận |
| B03-DN | Cash account 111/112/113, event classifier theo counterpart/voucher, metric source và fail-closed | Pass kỹ thuật | Sample rollback: `cash_flow_exceptions=[]`, `unresolved_line_codes=[]`, dòng 50 = 170.000.000, đầu kỳ = 100.000.000, cuối kỳ = 270.000.000, native closing cash = 270.000.000 |
| B09-DN | Native `Letron VAS Report Package`, note source refs, lifecycle guard | Pass kỹ thuật | Sample đã kiểm tra `Draft → Review → Closed → Issued` trong rollback; accounting input không bị tự sinh |
| Chống ghi đè/sai nguồn | Report chỉ đọc GL; sample tạo Journal Entry native, không insert GL trực tiếp; package lưu policy hash/source cutoff | Pass | Có audit trail kỹ thuật; vẫn cần chứng từ nguồn thật |
| Runtime/config drift | `docker-start.ps1 -Action verify` | Pass | HTTP health `ok=true`, config/policy `in-sync`, `drift_count=0`, `restart_required=false`, setup complete |
| Test code | Unit/integration acceptance hiện có | Pass kỹ thuật | Lần chạy hiện tại: `130 passed`; targeted `ruff` và `ty` cho phần thay đổi đều pass |
| Gateway TT99 thật | Letron API Gateway, không gọi trực tiếp ERPNext/Lark | Blocked bởi ERP SSO identity | Auth policy đã cấp quyền; Gateway tới ERP trả `403` với `Gateway identity is not an active ERP identity` |

## Findings và blocker

### TT99-01 — Operational gate — dữ liệu kỳ báo cáo và sign-off

Đây **không phải blocker readiness của hệ thống**. Fixture
`config/fixtures/tt99/tt99-vnd-realistic.json` chỉ tạo dữ liệu mô phỏng trong
transaction rollback-safe. Nó chứng minh lifecycle và phép đối chiếu native,
không chứng minh số liệu thực tế của Letron.

Để đóng gate cần chạy trên site acceptance có bản sao dữ liệu thật hoặc một
period được accounting owner chỉ định, sau đó lưu evidence của từng báo cáo:

- B01: trial balance, opening/closing balance và phân loại maturity;
- B02: doanh thu, chi phí, thuế, EPS và kỳ comparative;
- B03: bank/cash reconciliation, phân loại operating/investing/financing và
  `50 + 60 + 61 = 70`;
- B09: từng note bắt buộc, source refs, hồ sơ cam kết/sự kiện sau ngày khóa sổ.

### TT99-02 — P1 có điều kiện — phạm vi hợp nhất nâng cao

Package hợp nhất hiện có intercompany matching/elimination, BS/P&L/B03 và
comparative. NCI, deferred tax và FX translation chưa phải capability hoàn
chỉnh trong phạm vi hiện tại. Nếu báo cáo hợp nhất của doanh nghiệp cần các
chỉ tiêu này, phải bổ sung policy source, native adjustment workflow, test và
accounting acceptance; không được coi package hiện tại là đã đủ.

### TT99-03 — P1 có điều kiện — mẫu ngoài báo cáo năm

Các mẫu không hoạt động liên tục và giữa niên độ chưa nằm trong contract hiện
tại. Nếu kỳ lập báo cáo thực tế thuộc các trường hợp đó, cần thêm form/mapping,
comparative rule, package lifecycle và acceptance riêng trước khi phát hành.

### TT99-04 — P1 — transaction coverage chưa thay thế business acceptance

Sample hiện dùng native Journal Entry để tạo các event tiền, thuế, lãi vay,
TSCĐ, vay, vốn góp và cổ tức. Nó chưa phải một bộ chứng từ hoàn chỉnh
Sales/Purchase Invoice → Payment Entry → GL cho từng nghiệp vụ sản xuất. Đây là
việc cần bổ sung khi accounting owner yêu cầu kiểm tra xuyên suốt từ chứng từ
nguồn; không cần đổi định dạng fixture JSON hay xây ledger riêng.

### TT99-05 — Deployment gate — ERP identity cho Gateway acceptance

Contract, registry, Gateway route mapping, ERP handler và Auth entitlement đã
được triển khai. Nghiệm thu HTTP thật qua Letron API Gateway chưa thể chạy tiếp
vì ERP không có `Letron SSO Identity` active cho stable identity của Global
Admin. Cần hoàn tất JIT qua flow Lark SSO thật, rồi chạy lại Gateway
acceptance; không tạo User bằng email, không bypass bằng secret và không gọi
thẳng ERPNext trong test.

## Quyết định và hành động tiếp theo

| Ưu tiên | Hành động | Chủ trì | Điều kiện đóng |
|---|---|---|---|
| Operational | Chọn period và snapshot dữ liệu acceptance thật | Accounting + ERP | Có danh sách chứng từ và số dư được phê duyệt làm baseline |
| Operational | Chạy B01/B02/B03/B09 trên dữ liệu thật, đối chiếu từng dòng | Accounting + ERP | Không còn unresolved/exception; biên bản reconciliation được ký |
| Operational | Phát hành package B09 sau review | Accounting owner | Package `Issued`, source refs đầy đủ, không sửa được sau issue |
| P1 | Quyết định có cần NCI/deferred tax/FX và giữa niên độ không | CFO/Accounting | Ghi rõ in-scope/out-of-scope cho kỳ báo cáo |
| P1 | Nếu có, mở change riêng cho policy/backend/test của các capability đó | ERP | Có acceptance runtime tương ứng trước release |

## Lệnh tái kiểm tra kỹ thuật

Các lệnh dưới đây không thay thế sign-off nghiệp vụ:

```powershell
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action verify
.\scripts\apply_tt99_sample.ps1 -IssueB09
```

Lệnh sample mặc định rollback toàn bộ. Chỉ dùng `-Commit` trên site acceptance
đã được phê duyệt và có backup/rollback plan.

## Trạng thái cuối

| Kết luận | Trạng thái |
|---|---|
| Policy/config kỹ thuật | Đạt |
| Runtime zero-drift | Đạt |
| Native B03/B09 sample | Đạt |
| System readiness cho báo cáo thật | **READY** ở backend trong scope B01/B02/B03/B09 năm; chờ ERP SSO identity để mở Gateway |
| Production/statutory data acceptance | Operational gate theo từng kỳ |
| Accounting owner sign-off | Operational gate theo từng kỳ |
| Có cần sửa thêm code ngay không | Không, trong scope hiện tại |
| Có blocker hệ thống không | **Có deployment gate** — ERP SSO identity chưa được JIT materialize |
| Có blocker nếu mở rộng scope không | Có điều kiện — NCI/deferred tax/FX/interim/non-continuing |
