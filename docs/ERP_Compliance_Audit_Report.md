# Báo cáo Audit tuân thủ ERP

**Ngày audit:** 2026-08-14  
**Đối tượng:** Letron ERP trên ERPNext 16.31.1  
**Phạm vi:** Kiểm soát kế toán, thuế và dữ liệu nghiệp vụ thuộc trách nhiệm của ERP

## 1. Kết luận điều hành

Hệ thống có nền tảng ERP phù hợp để ghi nhận và xử lý nghiệp vụ kế toán, thuế,
kho và công nợ. Core policy, tax routing và các luồng invoice/GL đã có bằng
chứng acceptance trên disposable tenant. Tuy nhiên, chưa đủ cơ sở để kết luận
hệ thống đã hoàn tất tuân thủ pháp luật trong môi trường production.

Trạng thái audit: **CONDITIONAL — chưa đủ điều kiện đóng audit**.

Nguyên nhân chính không phải do ERP phải tự phát hành hóa đơn điện tử. Phát hành,
ký số, cấp mã và gửi hóa đơn điện tử là trách nhiệm của provider và integration
của Headless BE. Trách nhiệm của ERP là tạo dữ liệu giao dịch chính xác, tính
thuế và giá trị kế toán đúng, lưu liên kết/trạng thái trả về, đồng thời bảo toàn
vòng đời và dấu vết kiểm toán của chứng từ.

## 2. Cơ sở pháp lý tham chiếu

Audit sử dụng các văn bản hiện hành có liên quan trực tiếp đến dữ liệu và kiểm
soát mà ERP phải hỗ trợ:

- [Luật Kế toán 88/2015/QH13](https://vanban.chinhphu.vn/?docid=183198&pageid=27160).
- [Luật Thuế giá trị gia tăng 48/2024/QH15](https://vanban.chinhphu.vn/?docid=212476&pageid=27160), có hiệu lực từ 01/07/2025.
- [Nghị định 181/2025/NĐ-CP](https://vanban.chinhphu.vn/?docid=214336&lead=DGMKT&pageid=27160) quy định chi tiết một số nội dung về thuế GTGT.
- [Nghị định 70/2025/NĐ-CP](https://vanban.chinhphu.vn/?docid=213179&lang=vi&pageid=27160), sửa đổi quy định về hóa đơn, chứng từ, có hiệu lực từ 01/06/2025.

Các văn bản trên là căn cứ để xác định yêu cầu kiểm soát. Audit này không thay
thế quyết định nghiệp vụ của kế toán trưởng, tư vấn thuế hoặc cơ quan quản lý.

## 3. Ranh giới trách nhiệm

### 3.1. ERP phải chịu trách nhiệm

- Company, fiscal year, currency và account mapping được xác định đúng.
- Master data và Tax Template được liên kết đúng Company.
- Tính net total, tax, grand total, exchange rate và các giá trị base currency.
- Sinh GL Entry, Stock Ledger Entry và các ledger liên quan qua native controller.
- Kiểm soát submit, cancel, return/amend và các thay đổi sau khi chứng từ đã ghi sổ.
- Kiểm soát ngày hạch toán, kỳ kế toán, back-dated transaction và immutable ledger
  theo chính sách doanh nghiệp.
- Cung cấp dữ liệu đầy đủ cho integration e-invoice và lưu trạng thái/định danh
  trả về từ provider.
- Lưu audit trail, dữ liệu đối chiếu và khả năng truy xuất chứng từ nguồn.

### 3.2. Không thuộc `policy.yaml`

- Ký số và quản lý certificate.
- Cấp mã hoặc gửi hóa đơn đến cơ quan thuế.
- Quyết định hàng hóa/dịch vụ thuộc mức thuế nào.
- Quyết định accounting regime, tax matrix và account mapping thay cho kế toán.
- Khai thuế, nộp thuế và chịu trách nhiệm pháp lý thay doanh nghiệp.
- Chính sách lưu trữ hồ sơ pháp lý ở tầng hạ tầng/compliance storage.

## 4. Bằng chứng đã kiểm tra

| Hạng mục | Kết quả |
|---|---|
| `config/policy.yaml` | YAML hợp lệ, 26 DocType cấu hình |
| `config/policy-full.yaml` | YAML hợp lệ, 15 DocType; chỉ là fallback/reference |
| Bundle validation | Pass |
| Full unit test suite | 59 passed |
| Public invoice API | Có Sales Invoice/Purchase Invoice và lifecycle submit/cancel |
| Native controller boundary | Có sử dụng controller ERPNext; không thấy public route ghi trực tiếp ledger |
| Tax policy readback | Pass: Tax Category, Tax Rule, Tax Template và Item Tax Template |
| Configured invoice/GL acceptance | Pass: software 0%; hosting 10%; transport 10%, cho cả Sales/Purchase và GL |
| E-invoice handoff boundary | Có contract MISA, idempotency/status validation; chưa có provider stub/runtime adapter |
| Docker runtime acceptance | Focused acceptance pass trên disposable tenant; chưa chạy full suite |

Các test unit và validation chứng minh tính hợp lệ kỹ thuật của cấu hình, nhưng
không tự chứng minh dữ liệu nghiệp vụ thực tế của doanh nghiệp đã đúng pháp luật.

## 5. Findings

### F-01 — Mâu thuẫn ownership của `Global Defaults`

**Mức độ:** Medium  
**Trạng thái:** Resolved

Trước remediation, `contracts/scope.yml` khai báo `Global Defaults` là `managed`,
owner là `policy`, trong khi `config/policy.yaml` đã loại bỏ DocType này và tài
liệu mô tả nó là system-derived/excluded.

**Rủi ro:** Người vận hành không biết `Global Defaults` là nguồn cấu hình độc lập,
được suy ra từ bootstrap hay vẫn phải khai báo trong policy. Điều này làm sai
phạm vi kiểm soát và có thể tạo drift giữa scope, policy và runtime.

**Đã xử lý:** `Global Defaults` hiện được phân loại là `system`, owner là
`bootstrap` trong `contracts/scope.yml`; không được apply như một document của
operational policy.

### F-02 — `Accounting Period` chưa thống nhất classification

**Mức độ:** Medium  
**Trạng thái:** Closed trong phạm vi kiểm soát Accounting Period của ERPNext

`scope.yml` khai báo `Accounting Period` là `managed`. Policy hiện đã có record
`FY 2026 - LTVN`, từ 2026-01-01 đến 2026-08-14, thuộc Company `Letron Việt Nam`.
Focused acceptance đã xác nhận record native, các `closed_documents` đang mở và
hành vi native trên disposable tenant:

- chứng từ `Sales Invoice` trong kỳ được phép khi cờ đóng là `0`;
- ngày ngoài kỳ không bị hook đóng kỳ chặn — đúng với semantics native của
  `Accounting Period`, vì DocType này không phải global date-range validator;
- khi `Sales Invoice.closed = 1`, chứng từ cùng loại trong kỳ bị chặn;
- `exempted_role: null` không tạo quyền bypass.

**Phạm vi còn lại:** Việc mở/đóng kỳ vẫn là thao tác vận hành phải được kiểm soát
qua quyền ERPNext và quy trình phê duyệt nội bộ. Policy không tuyên bố rằng mọi
giao dịch ngoài khoảng ngày sẽ tự động bị từ chối.

Khi sang kỳ mới, phải cập nhật `end_date` theo ngày thực tế và không đặt ngày kết
thúc trong tương lai. Nếu doanh nghiệp cần chặn toàn bộ giao dịch ngoài kỳ, phải
bổ sung một control riêng; không được suy diễn chức năng đó từ `Accounting Period`.

### F-03 — Tax matrix trong policy chưa đầy đủ

**Mức độ:** High nếu dùng cho production  
**Trạng thái:** Closed về policy boundary; external master-data dependency nằm ngoài scope

Policy hiện đã khai báo Tax Template VAT 10% và nhóm software non-VAT tại
[`config/policy.yaml`](../config/policy.yaml). Các Tax Category/Tax Rule cho
software, hosting và vận tải nội địa đã có. Runtime readback và invoice/GL
acceptance đã xác nhận các route hiện tại trên disposable tenant:

- Software license/service: VAT `0%` và không phát sinh VAT GL.
- Hosting: VAT `10%` và GL tương ứng.
- Vận tải nội địa: VAT `10%` và GL tương ứng.

Đối chiếu pháp lý sơ bộ với Luật Thuế GTGT số 48/2024/QH15: Điều 5 khoản 21
liệt kê sản phẩm phần mềm và dịch vụ phần mềm vào nhóm không chịu VAT; Điều 9
khoản 3 đặt mức 10% cho hàng hóa/dịch vụ không thuộc nhóm 0% hoặc 5%. Luật có
hiệu lực từ 2025-07-01. Đây là căn cứ kiểm tra, không thay thế hồ sơ hợp đồng
và phê duyệt của kế toán trưởng.

**Phát hiện nghiêm trọng:** `VAT - LTVN` đang được dùng cho cả Sales và Purchase.
Readback native cho thấy Account này là `account_type: Tax`, `root_type: Liability`;
đây là mapping VAT đầu ra. Chưa có Input VAT Account thuộc nhóm Asset cho Purchase.
Vì vậy test tax amount/GL hiện tại chỉ chứng minh phép tính, chưa chứng minh
định khoản VAT đầu vào đúng.

Account là master data ngoài phạm vi `policy.yaml`. Audit policy không được tự
tạo hoặc sửa Account trong DB. Vì vậy phần này được đóng ở boundary của policy;
việc chứng nhận accounting mapping thực tế phải thuộc quy trình master-data và
kiểm toán kế toán riêng.

Ngoài ra, policy chưa chứng minh các trường hợp 0%, 5%, 8%, miễn thuế và các
trường hợp đầu vào/đầu ra khác nhau đã được cấu hình đúng cho doanh nghiệp.

**Đầu ra đã tạo:** Bản dự thảo tax matrix nằm tại
[`docs/Tax_Matrix_Approval.md`](Tax_Matrix_Approval.md). Kế toán trưởng phải phê
duyệt tax matrix; sau đó cấu hình Tax
Category, Tax Rule, Sales/Purchase Tax Template và Item Tax Template tương ứng.
Không tự thêm mức thuế chỉ dựa trên suy đoán từ code. Không đổi Purchase
`account_head` sang tên đoán trước khi Account thật được tạo và readback.

### F-04 — Chưa có e-invoice handoff contract đầy đủ

**Mức độ:** Medium  
**Trạng thái:** Closed về ERP handoff contract; MISA provider runtime ngoài scope

Việc phát hành và gửi hóa đơn điện tử nằm ngoài `policy.yaml` là đúng boundary.
Tuy nhiên chưa thấy contract/runtime evidence đầy đủ cho phần ERP phải bàn giao và
nhận lại:

- provider invoice ID;
- invoice number/series;
- trạng thái issued/rejected/cancelled/adjusted;
- mã cơ quan thuế;
- liên kết hóa đơn thay thế/điều chỉnh;
- timestamp và lỗi trả về từ provider.

**Đã xử lý:** Contract boundary đã được tạo tại
[`contracts/einvoice-handoff.yml`](../contracts/einvoice-handoff.yml). Contract,
idempotency key, required payload fields và provider-status validation đã có ở
lớp ERP handoff. Phát hành, ký số, gửi/nhận trạng thái thực tế và persistence
với MISA là provider integration runtime, nằm ngoài policy/ERP acceptance hiện tại.

### F-05 — Candidate validation và runtime fallback

**Mức độ:** Không còn là finding  
**Trạng thái:** Closed by regression test

Runtime có cơ chế bổ sung field thiếu từ `policy-full.yaml`, nhưng candidate tạm
thời được tạo khi sửa qua control API có tên file khác. Tuy nhiên
`_load_full_defaults()` luôn tìm `policy-full.yaml` trong cùng thư mục bằng
`source.with_name("policy-full.yaml")`, ngoại trừ chính file `policy-full.yaml`.
Vì vậy candidate vẫn được resolve cùng fallback với runtime.

Không có bằng chứng hiện tại cho thấy candidate và policy runtime được resolve
thành hai effective state khác nhau.

**Đã kiểm chứng thêm:** Test đã bao phủ candidate path, tải trực tiếp
`policy-full.yaml`, effective hash và các giá trị explicit `0`, `null`, `''`,
`{}` và `[]`. Một lỗi khiến `{}` bị fallback ghi đè đã được sửa.

### F-06 — Thiếu bằng chứng runtime mới để đóng audit

**Mức độ:** Medium  
**Trạng thái:** Closed trong phạm vi policy-focused acceptance

Policy-focused Docker acceptance đã pass trên disposable tenant, bao phủ policy
bootstrap/sync, Accounting Period readback, Tax Category/Rule readback,
Sales/Purchase Invoice, tax calculation và GL reconciliation cho ba nhóm nghiệp
vụ hiện tại. Đây là phạm vi đúng của audit `policy.yaml`.

Các suite Stock Traceability, Accounts Reconciliation và full module lifecycle
không thuộc policy acceptance; chúng là acceptance riêng của module/API. Chúng
không còn được dùng làm điều kiện chặn F-06.

Đã thử chạy toàn bộ `tests/integration/test_policy_runtime.py`: `2 passed`, sau
đó `43 failed` vì host Windows trả `WinError 1455: The paging file is too small
for this operation to complete` khi tạo thêm các subprocess `docker exec`.
Đây là blocked runtime evidence, không được ghi nhận là full-suite pass. Cần
chạy lại sau khi giải phóng tài nguyên/tăng paging file hoặc dùng runner có đủ
memory; các node thay đổi phải tiếp tục chạy riêng để tránh nhiễu do tài nguyên.
Hai lần khởi động lại disposable tenant sau đó tiếp tục bị Docker Desktop lỗi
mount `/run/desktop/mnt/host/d/...: file exists`; đây là evidence của module/full
suite environment, không làm mở lại policy finding đã có focused evidence.

**Khuyến nghị ngoài F-06:** Chạy full module acceptance trên tenant disposable,
không dùng dữ liệu production; ghi nhận request, readback, GL/stock ledger,
cancel/amend và zero-residue evidence cho từng module.

## 6. Điểm đạt hiện tại

- Policy có cấu trúc rõ ràng và dùng UTF-8.
- Explicit values như `0`, `null`, `''`, `{}` và `[]` không bị coi là thiếu dữ liệu.
- Tax Template có liên kết Company, VAT account, Cost Center và tax rate.
- Invoice API có các trường quan trọng cho hạch toán và đối chiếu.
- Lifecycle của Invoice có submit/cancel rõ ràng.
- Policy không đưa secret, certificate hoặc executable customization vào YAML.
- `policy-full.yaml` được định vị là fallback kỹ thuật, không phải nguồn apply độc lập.
- Giá trị explicit `0`, `null`, `''`, `{}` và `[]` được bảo toàn khi merge fallback.

## 7. Điều kiện đóng audit

Audit chỉ được chuyển sang **PASS có điều kiện** khi hoàn thành tối thiểu:

1. Đồng bộ classification giữa `scope.yml`, policy và tài liệu.
2. Chốt ownership và test cho `Accounting Period`. **Đã đạt trong phạm vi F-02.**
3. Có tax matrix được kế toán trưởng phê duyệt, có Input/Output VAT Account
   đúng loại và cấu hình tương ứng. Phần Account master data là external gate,
   không thuộc scope triển khai policy.
4. Provider stub/adapter e-invoice và test trạng thái hai chiều, retry/deduplication
   là external integration gate, không thuộc scope policy hiện tại.
5. Policy-focused Docker acceptance và lưu lifecycle, cleanup, GL/tax
   reconciliation evidence. **Đã đạt trong phạm vi F-06.** Full module
   acceptance là gate riêng, không thuộc audit policy.

## 8. Kết luận cuối

Không có cơ sở để yêu cầu ERP tự thực hiện việc mua dịch vụ hóa đơn điện tử,
ký số hoặc gửi cơ quan thuế. Boundary hiện tại là hợp lý.

Các finding thuộc audit policy đã được xử lý theo boundary tương ứng. Các điểm
còn lại là external gate: phê duyệt tax/master data, MISA provider runtime và
full acceptance của từng module. Hệ thống có thể được xem là **ERP core policy
đã đạt policy-focused acceptance**, nhưng không đồng nghĩa toàn bộ ERP production
đã hoàn tất module acceptance hoặc legal sign-off.
