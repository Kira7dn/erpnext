# Handoff: ERPNext Purchase Order tới Lark Approval

## Ownership

ERPNext là source of truth cho Material Request, RFQ, Supplier Quotation và
Purchase Order. `apps/erp` điều phối luồng và là adapter Lark Approval: đọc dữ
liệu ERPNext, tạo approval instance, nhận webhook và submit PO.

Global Auth không tạo Lark Base record, không giữ trạng thái PO nghiệp vụ và
không xử lý Approval procurement. Webhook APPROVED chỉ submit đúng PO Draft đã được
ghi trong approval form; retry là idempotent theo tên PO và instance code.

## Routes hiện tại

- `apps/erp` gọi trực tiếp `openPurchaseApproval()` để tạo approval từ một PO
  native đã tồn tại.
- `POST /api/integrations/lark/webhooks/approval`: nhận và reconcile trạng thái
  approval.
- `POST /api/internal/lark/approval/reconcile`: reconcile nội bộ khi cần vận
  hành.

## Invariants

- Một orchestration có tối đa một PO Draft native.
- Một PO native được dùng xuyên suốt từ approval tới submit.
- Approval rejection/cancel chỉ cập nhật trạng thái PO, không tạo PO mới.
- Webhook duplicate không submit lại PO đã submitted.
- Lark Mail/Approval không được trở thành nơi lưu trạng thái procurement.

## Kiểm chứng tĩnh

Typecheck TypeScript và kiểm tra Python là gate hiện tại. Realtest Lark/ERPNext
được thực hiện riêng sau khi các contract runtime được triển khai.
