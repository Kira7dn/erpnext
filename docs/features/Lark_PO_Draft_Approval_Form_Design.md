# Lark Purchase Approval Form

Form approval chỉ là snapshot để người duyệt xem và quyết định. Dữ liệu gốc
được đọc từ ERPNext ngay trước khi tạo approval.

## Thông tin form

- Lý do mua hàng
- Thông tin tham chiếu: PO, MR, RFQ, Supplier Quotation và orchestration
- Loại mua hàng
- Ngày cần giao hàng
- Điều khoản thanh toán
- Điều kiện giao hàng
- Chi tiết mua hàng theo từng dòng: hàng hóa, mô tả, số lượng, đơn giá, thành tiền

PO native đã tạo tại ERPNext được ghi trong phần tham chiếu và được dùng lại
nguyên trạng khi webhook APPROVED submit chứng từ.

## Contract

Server operation `openPurchaseApproval()` nhận `orchestration_id`,
`supplier_quotation_name`, `erp_purchase_order_name` và `justification`.

`POST /api/integrations/lark/webhooks/approval` đọc approval instance, xử lý
REJECTED/CANCELED bằng cách cập nhật metadata trên PO, hoặc submit đúng PO Draft
khi APPROVED.

Không có Lark Base projection, PO draft ID của Lark hoặc route tạo PO riêng.
