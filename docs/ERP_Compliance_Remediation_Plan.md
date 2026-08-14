# Kế hoạch xử lý các Finding Audit ERP

**Ngày lập:** 2026-08-13  
**Căn cứ:** [ERP Compliance Audit Report](ERP_Compliance_Audit_Report.md)

## Nguyên tắc xử lý

- Chỉ sửa các lớp thuộc trách nhiệm của ERP.
- Không đưa tax interpretation, secret, certificate hoặc e-invoice signing vào
  `policy.yaml`.
- Không tự điền mức thuế khi chưa có tax matrix được kế toán phê duyệt.
- Mọi thay đổi phải có policy validation, native controller readback và runtime
  acceptance tương ứng.

## F-01 — Global Defaults

### Nguyên nhân

Trước remediation, `scope.yml` coi `Global Defaults` là `managed/policy`, nhưng
policy vận hành không khai báo record này vì country, currency và company đã có owner là
`policy.bootstrap.company`.

### Phương án được đề xuất

Bản dự thảo để kế toán điền và phê duyệt đã được tạo tại
[`docs/Tax_Matrix_Approval.md`](Tax_Matrix_Approval.md). Chưa đưa các dòng
`Pending` vào policy.

Giữ thiết kế hiện tại; ownership đã được sửa trong `contracts/scope.yml`:

```yaml
- name: Global Defaults
  classification: system
  source_type: frappe
  owner: bootstrap
  selector: single
```

Không đưa `Global Defaults` trở lại `config/policy.yaml`. `policy-full.yaml` cũng
không được xem là nguồn apply độc lập.

### Acceptance còn lại

- `policy validate` vẫn pass.
- `bundle-validate` xác nhận country/currency/company từ bootstrap.
- Không còn tài liệu nào mô tả `Global Defaults` là policy-managed.
- Test xác nhận không có mirror country/currency trong `config/config.yaml`.

## F-02 — Accounting Period

### Nguyên nhân

DocType đã được scope và có native acceptance fixture, nhưng tài liệu ghi
`conditional` trong khi `scope.yml` ghi `managed`; policy production trước đây
chưa có record Accounting Period.

### Phương án được đề xuất

Đối với hệ thống ERP dùng để ghi sổ chính thức, chọn `managed` và khai báo từng
kỳ kế toán được phép sử dụng trong policy. Policy hiện đã khai báo `FY 2026 - LTVN`
từ 2026-01-01 đến 2026-08-14; khi sang kỳ mới phải cập nhật record theo ngày
thực tế và không đặt `end_date` trong tương lai.
Không dùng một field toàn cục kiểu
`allow_backdated` để thay thế Accounting Period.

Mỗi record cần thể hiện tối thiểu:

- `period_name`;
- `start_date`;
- `end_date`;
- `company`;
- `closed_documents` theo native ERPNext.

Nếu doanh nghiệp quyết định kỳ kế toán do hệ thống khác quản lý, phải đổi
classification thành `conditional`, đổi owner khỏi policy và bổ sung contract
kiểm tra kỳ trước khi submit chứng từ.

### Acceptance

- Tạo/readback một kỳ thuộc đúng Company.
- Chứng từ trong kỳ được native hook cho phép khi DocType chưa đóng.
- Xác nhận ngày ngoài kỳ không bị hook `Accounting Period` chặn; đây là giới hạn
  native phải được ghi rõ, không coi là lỗi của policy.
- Đóng một loại chứng từ trong kỳ làm chứng từ cùng loại bị native hook chặn.
- `exempted_role: null` không tạo bypass.
- Cancel/amend không phá vỡ audit trail được theo dõi ở acceptance lifecycle riêng.

## F-03 — Tax matrix

### Nguyên nhân

Policy hiện có Tax Template VAT 10%, software non-VAT template và các Tax
Category/Tax Rule theo hoạt động đã cung cấp. Native runtime readback vẫn chưa
được chạy trên tenant production/disposable hiện tại.

### Phương án được đề xuất

Kế toán trưởng phê duyệt một tax matrix ngoài code trước. Sau đó đưa các master
data đã được phê duyệt vào policy vì đây là cấu hình pháp lý có version và cần
reproduce được khi đóng gói tenant:

- Sales Taxes and Charges Template;
- Purchase Taxes and Charges Template;
- Item Tax Template;
- Tax Category;
- Tax Rule;
- effective date và Company;
- VAT account và Cost Center.

Không mặc định rằng mọi doanh nghiệp đều phải có đủ 0%, 5%, 8% và 10%. Policy
chỉ chứa các trường hợp thực sự được doanh nghiệp phê duyệt và áp dụng.

### Acceptance

Trước khi close F-03, phải xử lý riêng mapping VAT đầu vào/đầu ra:

- `Sales` dùng Output VAT Account thuộc `Liability`;
- `Purchase` dùng Input VAT Account thuộc `Asset`;
- nếu có VAT đầu vào không được khấu trừ, dùng Account chi phí/tài sản riêng
  theo quyết định của kế toán trưởng;
- readback phải xác nhận `Company`, `root_type`, `account_type` và template
  thực tế, không chỉ xác nhận tax amount.

Không được đổi `account_head` sang tên suy đoán trong policy. Account là
master data ngoài phạm vi policy; việc tạo/sửa Account trong DB phải được xử lý
bởi quy trình master-data riêng. Chỉ sau khi Account thật đã tồn tại và được
kế toán xác nhận mới đưa tên đó vào policy.

Phần master-data này là external gate và không phải điều kiện triển khai của
policy hiện tại.

Với từng dòng trong tax matrix:

- chọn đúng template theo Tax Category/Tax Rule;
- tạo Sales Invoice và Purchase Invoice;
- kiểm tra tax amount;
- submit chứng từ;
- đối chiếu debit/credit trong GL Entry;
- kiểm tra currency và rounding;
- cancel/amend và đối chiếu reversal.

Các test phải đọc tax matrix làm input, không hard-code kết quả theo một mức thuế
duy nhất.

## F-04 — E-invoice handoff

### Nguyên nhân

ERP boundary đúng khi không đặt provider, certificate hoặc signing vào policy.
Phần còn thiếu là contract dữ liệu giữa Invoice trong ERP và provider.

### Phương án được đề xuất

Tạo contract riêng, ví dụ `contracts/einvoice-handoff.yml`, mô tả:

- source document: Sales Invoice/Purchase Invoice nếu provider hỗ trợ;
- immutable source identity: Company, doctype, name, posting date;
- seller/buyer tax identity;
- line, tax, total và currency snapshot;
- idempotency key;
- provider invoice ID, invoice number/series và tax authority code;
- trạng thái `pending | submitted | issued | rejected | cancelled | adjusted`;
- liên kết hóa đơn gốc/thay thế/điều chỉnh;
- retry, timeout và lỗi;
- quyền cập nhật trạng thái và audit timestamp.

Integration state nên nằm ở Headless BE/provider integration store hoặc DocType
integration riêng; không sửa ngược các giá trị derived của Invoice và không lưu
secret trong policy.

### Acceptance

- Cùng một Invoice không tạo hai request phát hành khi retry.
- Provider response được lưu và đọc lại được.
- Rejected không làm Invoice tự động thành issued.
- Cancel/adjusted giữ liên kết với Invoice gốc.
- Mất kết nối provider không làm mất chứng từ kế toán đã submit.

Các kiểm tra trên thuộc provider integration runtime. Trong scope ERP policy hiện
tại, đã close phần contract schema, required payload fields, idempotency key và
provider-result validation; không giả lập việc MISA phát hành hoặc ký số.

## F-05 — Candidate/runtime fallback

### Kết quả nghiên cứu

Finding này đã được đóng. Code hiện tại dùng
`source.with_name("policy-full.yaml")`, nên file candidate tạm vẫn dùng fallback
ở cùng thư mục. Không cần sửa production code.

### Việc cần giữ

- regression test cho candidate path;
- test explicit `0`, `null`, `''`, `{}` và `[]` không bị fallback ghi đè;
- test tải trực tiếp `policy-full.yaml` không tự merge chính nó;
- effective hash được dùng trong bundle evidence.

## F-06 — Runtime evidence

### Nguyên nhân

Unit test chứng minh schema và pure logic, nhưng policy audit cần thêm native
runtime readback và đối chiếu tax/GL. Full Stock/Accounts/module lifecycle là
acceptance riêng, không phải điều kiện đóng policy.

### Phương án được đề xuất

Policy-focused acceptance trên disposable tenant gồm:

1. Bootstrap, Company, Fiscal Year và Accounting Period.
2. Tax Category/Tax Rule/Tax Template.
3. Sales Invoice và Purchase Invoice với từng tax matrix row.
4. Submit/cancel và GL reconciliation trong các route thuế đã khai báo.
5. Policy drift, idempotency, cleanup, zero residue và bundle hash.

Stock transaction, valuation, Stock Ledger, Accounts Reconciliation và MISA
provider runtime thuộc acceptance riêng của module/integration.

Mỗi nhóm phải lưu request, response, native readback, ledger readback, expected
result và cleanup result. Test timeout hoặc test bị terminate không được ghi là
pass.

Lần chạy full `tests/integration/test_policy_runtime.py` ngày 2026-08-14 bị
block bởi `WinError 1455` của host khi tạo subprocess Docker. Kết quả đó không
được tính là pass; phải chạy lại trên host đủ paging/memory và lưu evidence mới.
Các lần khởi động disposable tiếp theo còn gặp lỗi Docker Desktop mount
`/run/desktop/mnt/host/d/...: file exists`; đây cũng là blocked evidence, không
được coi là test failure của nghiệp vụ.

## Thứ tự triển khai

1. Sửa classification `Global Defaults` và thống nhất tài liệu.
2. Chốt ownership của `Accounting Period`.
3. Nhận tax matrix đã phê duyệt và đưa master data vào policy.
4. Tạo e-invoice handoff contract.
5. Thêm/điều chỉnh acceptance test theo tax matrix và kỳ kế toán.
6. Chạy Docker runtime acceptance và phát hành audit evidence.

## Tiêu chí đóng remediation

Chỉ đóng remediation khi cả ba lớp đều đạt:

1. **Configuration:** policy/scope/docs không mâu thuẫn.
2. **Runtime:** native controller, invoice calculation và ledger readback đúng.
3. **Evidence:** policy-focused test artifact có thể truy xuất, không còn test timeout được ghi
   nhầm là pass và tenant disposable đã cleanup sạch.
