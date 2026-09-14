# TT99 sample acceptance

## Quyết định định dạng

Fixture được lưu bằng JSON tại
`config/fixtures/tt99/tt99-vnd-realistic.json` vì JSON:

- review và diff tốt trong Git;
- biểu diễn được cả giao dịch, kỳ hiện tại/kỳ so sánh và B09 accounting input;
- không phụ thuộc database hoặc engine phân tích;
- phù hợp với số lượng fixture nhỏ, có cấu trúc và cần tái sử dụng.

CSV chỉ nên dùng khi nhập bảng dòng lớn từ kế toán. Parquet phù hợp cho phân tích
dữ liệu lớn, không phù hợp làm source-of-truth cho acceptance. Database chỉ là
đích native ERPNext sau khi apply, không phải nơi lưu fixture chuẩn.

## Cách chạy

Mặc định runner tạo Journal Entry native, sinh GL thật, kiểm tra B03/B09 rồi
rollback toàn bộ:

```powershell
.\scripts\apply_tt99_sample.ps1
```

Kiểm tra cả bước phát hành B09 nhưng vẫn rollback:

```powershell
.\scripts\apply_tt99_sample.ps1 -IssueB09
```

Chỉ dùng `-Commit` trên site acceptance/disposable đã được chỉ định:

```powershell
.\scripts\apply_tt99_sample.ps1 -Commit -IssueB09
```

Có thể chọn fixture khác nằm dưới `config`:

```powershell
.\scripts\apply_tt99_sample.ps1 -SamplePath fixtures/tt99/my-sample.json
```

## Bằng chứng được kiểm tra

Runner `letron_api.control.tt99_sample.apply`:

1. validate schema, kỳ, mã tài khoản và cân đối Nợ/Có;
2. resolve account number sang native Account theo Company;
3. submit Journal Entry native, không chèn trực tiếp GL Entry;
4. đối chiếu dòng tiền cash account 111/112/113 với B03 dòng 50 và số dư cuối kỳ;
5. tạo package B09 native, lưu `source_refs`, rồi kiểm tra `Draft → Review → Closed`
   và tùy chọn `Issued`;
6. rollback mặc định, hoặc commit chỉ khi caller truyền `-Commit`.

Đây là bằng chứng runtime kỹ thuật. Nó không thay thế dữ liệu giao dịch thật,
nguồn chứng từ thật hoặc phê duyệt của accounting owner cho báo cáo chính thức.

## Kết quả kiểm tra gần nhất — 2026-09-14

Đã chạy lại:

```powershell
.\docker-start.ps1 -Action policy-validate
.\docker-start.ps1 -Action verify
.\scripts\apply_tt99_sample.ps1 -IssueB09
```

Kết quả: policy `ok=true`, 90 managed documents, completeness không có lỗi,
runtime config/policy `in-sync`, `drift_count=0`; sample rollback trả B03 không
có exception/unresolved line, dòng 50 là `170.000.000`, đầu kỳ là
`100.000.000`, cuối kỳ là `270.000.000` và khớp native closing cash
`270.000.000`. B09 đạt trạng thái `Issued` (`docstatus=1`) trong transaction
rollback.

Kết quả này chỉ đóng technical acceptance. Release statutory vẫn cần chạy trên
period/dữ liệu thật do accounting owner chỉ định và lưu biên bản reconciliation
cho B01/B02/B03/B09. Chi tiết blocker và điều kiện đóng nằm trong
[`TT99_2025_Compliance_Audit_2026-09-14.md`](../audits/TT99_2025_Compliance_Audit_2026-09-14.md).
