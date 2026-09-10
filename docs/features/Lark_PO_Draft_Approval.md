# Purchase Order Approval

## Mục tiêu

Lark chỉ cung cấp giao diện và trạng thái phê duyệt. ERPNext giữ toàn bộ dữ
liệu procurement và là source of truth duy nhất.

## Luồng

```text
MR -> RFQ -> Supplier Quotation -> chọn giá thấp nhất
   -> ERPNext Purchase Order Draft -> Lark Approval
   -> webhook APPROVED -> submit đúng Purchase Order đó
```

`apps/erp` tạo PO Draft native và truyền tên PO vào adapter. Auth Server đọc
MR/RFQ/Supplier Quotation/PO qua Frappe REST, dựng form approval và gọi Lark.
Auth Server không tạo Lark Base projection, không lưu PO state riêng và không
tạo PO thay ERPNext.

## Idempotency

- Một orchestration chỉ tạo một PO Draft native.
- Lark Approval dùng UUID xác định từ `orchestration_id` và tên PO.
- Webhook dùng Redis lock/dedupe key ở `apps/erp` để dedupe event.
- Callback APPROVED kiểm tra PO đã submitted; nếu rồi thì trả idempotent.
- Không tạo PO mới khi approval retry.

## Trạng thái PO

Approval status được ghi trên chính Purchase Order native qua các custom field
`custom_lark_approval_status`, `custom_lark_approval_instance_code` và
`custom_lark_error`. Đây là metadata tích hợp, không phải một bản sao nghiệp vụ.

## Routes

- Supplier quotation flow gọi trực tiếp `openPurchaseApproval()` server-side.
- `POST /api/integrations/lark/webhooks/approval`
- `POST /api/internal/lark/approval/reconcile`
