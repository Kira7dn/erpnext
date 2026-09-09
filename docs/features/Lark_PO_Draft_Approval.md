# Lark PO Draft và Approval

> **Implementation status:** Server-side handoff is connected. When a selected
> Supplier Quotation is supplied, the orchestration creates/reuses the Lark PO
> Draft and Approval instance; without one, the RFQ remains pending handoff.
> Live tenant acceptance is still pending. See [handoff note](Lark_PO_Draft_Approval_Handoff.md).

Form Approval chi tiết: [Lark PO Draft Approval Form Design](Lark_PO_Draft_Approval_Form_Design.md).

## 1. Quyết định kiến trúc

Lark là nơi sở hữu bản nháp và vòng đời phê duyệt Purchase Order. Global
Portal là integration owner vì đang liên kết với Lark, giữ session và gọi Lark
Open API. ERPNext chỉ nhận Purchase Order snapshot sau khi đã được Lark duyệt.

```text
Material Request → Request for Quotation → Supplier Quotation
                                      ↓
                              Lark Base: PO Draft
                                      ↓
                           Lark Approval: Pending
                                      ↓ Approved
                         Global Portal → ERPNext PO
```

`apps/erp` chỉ hiển thị nghiệp vụ và gọi API của Global Portal; không tạo PO
ERPNext trước khi có approval hợp lệ.

## 2. Trách nhiệm từng hệ thống

### Lark Base

- Lưu PO Draft và các dòng item.
- Cho phép sửa supplier, item, quantity, rate, warehouse và điều khoản mua.
- Lưu trạng thái nghiệp vụ: `Draft`, `Pending Approval`, `Approved`,
  `Rejected`, `Canceled`, `Sent to ERP`, `ERP Submitted`.
- Lưu liên kết Material Request, RFQ, Supplier Quotation và ERP Purchase Order.

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
- Tạo và cập nhật PO Draft trong Lark Base.
- Tạo Lark Approval instance.
- Nhận webhook/event, chống trùng theo `event_id`.
- Khi `Approved`, đọc lại Base và Approval, tạo approved snapshot rồi gọi
  endpoint ERPNext.
- Lưu integration log/idempotency; không tạo bản PO Draft thứ hai trong Portal.

### ERPNext

- Tiếp tục là nguồn chuẩn cho master data, tồn kho, ledger và chứng từ đã ghi
  nhận.
- Chỉ nhận snapshot đã được duyệt.
- Endpoint nên có dạng:

```text
POST /api/v1/buying/purchase-orders/from-approved-lark
```

Endpoint kiểm tra chữ ký nội bộ, `approval_instance_code`, `payload_hash` và
idempotency trước khi tạo và submit Purchase Order.

## 3. Trạng thái và xử lý kết quả

| Lark Approval | Lark Base | ERPNext |
|---|---|---|
| `PENDING` | Pending Approval | Chưa có PO |
| `APPROVED` | Approved / Sent to ERP | Tạo và submit PO |
| `REJECTED` | Rejected | Chưa có PO; cho phép tạo attempt mới |
| `CANCELED` | Canceled | Chưa có PO |

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
