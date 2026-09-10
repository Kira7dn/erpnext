# Lark PO Draft và Approval

> **Implementation status:** ERPNext is the SSOT. After the cheapest submitted
> Supplier Quotation is selected, the orchestration creates exactly one native
> ERPNext PO Draft and obtains its real PO number before opening Lark Approval.
> Approval callback submits that same ERPNext draft; it never creates a second
> PO. See [handoff note](Lark_PO_Draft_Approval_Handoff.md).

Form Approval chi tiết: [Lark PO Draft Approval Form Design](Lark_PO_Draft_Approval_Form_Design.md).

## 1. Quyết định kiến trúc

ERPNext sở hữu bản nháp, số chứng từ và vòng đời Purchase Order. Global Portal
là integration owner của Lark, giữ snapshot/idempotency và gọi Lark Open API.
Lark chỉ là projection của approval; không phải SSOT và không tự sinh số PO.

```text
Material Request → Request for Quotation → Supplier Quotation
                                      ↓ cheapest selected
                         ERPNext: native PO Draft (real PO number)
                                      ↓
                           Lark Approval: Pending
                                      ↓ Approved
                         Global Portal → ERPNext: submit same PO Draft
```

`apps/erp` chỉ hiển thị nghiệp vụ và gọi API của Global Portal; PO Draft được
tạo qua server-side control-plane trước approval, không qua browser.

## 2. Trách nhiệm từng hệ thống

### Lark Base (projection)

- Lưu PO Draft và các dòng item.
- Lưu snapshot để hiển thị/audit; không cho sửa nguồn ERPNext sau khi approval
  đã mở.
- Lưu trạng thái nghiệp vụ: `Draft`, `Pending Approval`, `Approved`,
  `Rejected`, `Canceled`, `Sent to ERP`, `ERP Submitted`.
- Lưu liên kết Material Request, RFQ, Supplier Quotation và ERP Purchase Order
  thật (`erp_purchase_order_name`).

Nên dùng bảng `PO Draft` và bảng `PO Draft Item` liên kết với nhau; không nhét
toàn bộ item list vào một JSON field duy nhất.

### Lark Approval

- Dùng một approval definition cố định, ví dụ `Purchase Order Approval`.
- Form hiển thị supplier, company, total, item, nguồn RFQ và link về Portal.
- Lưu và phát trạng thái approval qua `instance_code`.
- Theo dõi các event:
  `approval.instance.status_changed_v4` và
  `approval.task.status_changed_v4`.

### Global Portal

- Đọc MR/RFQ/Supplier Quotation từ ERPNext Gateway.
- Gọi ERPNext tạo PO Draft native trước, sau đó tạo projection PO Draft trong
  Lark Base có cùng số PO.
- Tạo Lark Approval instance.
- Nhận webhook/event, chống trùng theo `event_id`.
- Khi `Approved`, đọc lại Base và Approval, kiểm tra snapshot rồi gọi endpoint
  ERPNext để submit đúng `erp_purchase_order_name`.
- Lưu integration log/idempotency; không tạo bản PO Draft thứ hai trong Portal.

### ERPNext

- Tiếp tục là nguồn chuẩn cho master data, tồn kho, ledger và chứng từ đã ghi
  nhận.
- Tạo PO Draft từ payload đã validate trước approval; giữ `docstatus = 0`.
- Callback chỉ được submit draft đúng correlation/hash/attempt; không insert PO
  mới. Các route control-plane hiện dùng:

```text
POST /api/method/letron_api.lark_po.create_draft
POST /api/method/letron_api.lark_po.from_approved
POST /api/method/letron_api.lark_po.update_approval_state
```

Các endpoint kiểm tra chữ ký nội bộ, correlation, `approval_instance_code`,
`payload_hash`, attempt và idempotency.

## 3. Trạng thái và xử lý kết quả

| Lark Approval | Lark Base | ERPNext |
|---|---|---|
| `PENDING` | Pending Approval | PO Draft native, `docstatus=0` |
| `APPROVED` | Approved / Sent to ERP | Submit đúng PO Draft, giữ nguyên số |
| `REJECTED` | Rejected | Giữ PO Draft + trạng thái Rejected để audit/retry |
| `CANCELED` | Canceled | Giữ PO Draft, không submit |

Khi nhận `APPROVED`, Portal phải đọc lại approval instance và PO Draft, kiểm
tra snapshot chưa đổi, rồi mới gọi ERPNext. Không tin một webhook đơn lẻ và
không cho browser tự gọi thao tác submit.

## 4. Dữ liệu liên kết tối thiểu

Trong Lark Base:

```text
draft_id
material_request_name
request_for_quotation_name
supplier_quotation_name
approval_instance_code
approval_attempt
payload_hash
erp_purchase_order_name
```

Trong ERPNext Purchase Order đã tạo:

```text
custom_lark_draft_id
custom_lark_approval_instance_code
custom_lark_approval_attempt
custom_lark_payload_hash
```

Lark App Secret, tenant token và webhook verification chỉ nằm server-side
trong Global Portal; không đưa vào `apps/erp` browser bundle.

## 5. Tài liệu tham chiếu

- [Lark Approval instance API](https://open.larksuite.com/document/server-docs/approval-v4/instance/create)
- [Lark Approval events](https://github.com/larksuite/cli/blob/main/skills/lark-event/references/lark-event-approval.md)
- [Purchase accounting API flow](../Purchase_Accounting_API_Flow.md)
- [Global Portal README](../../apps/auth-server/README.md)
