# Thiết kế form `LeTRON PO Draft Approval`

> **Trạng thái triển khai:** Server-side handoff đã nối từ orchestration tới
> Global Portal khi có Supplier Quotation được chọn; UI cũng cho phép gửi sau
> nếu RFQ hoàn tất trước. Acceptance với Lark tenant thật vẫn còn pending. Xem
> [handoff note](Lark_PO_Draft_Approval_Handoff.md).

## 1. Mục tiêu và ranh giới

Material Request (MR), Request for Quotation (RFQ) và Supplier Quotation vẫn
được lấy từ ERPNext qua contract hiện hành. PO Draft được tạo và chỉnh sửa ở
Lark Base. Global Portal là integration owner: tạo snapshot, tạo Approval
instance, nhận trạng thái và gọi ERPNext sau khi được duyệt. ERPNext không tạo
PO trước approval và chỉ là nơi lưu chứng từ chính thức sau cùng.

```text
ERPNext MR -> ERPNext RFQ -> ERPNext Supplier Quotation
                                      |
                                      v
                          Global Portal -> Lark Base PO Draft
                                      |
                         immutable approval snapshot
                                      v
                              Lark Approval
                                      |
                         APPROVED -> Global Portal
                                      v
                           ERPNext Purchase Order
```

## 2. Ánh xạ dữ liệu từ contract

### 2.1. Material Request

Tạo và xác nhận MR bằng:

```text
POST /api/v1/stock/material-requests
POST /api/v1/stock/material-requests/{name}/submit
```

Trường bắt buộc theo contract: `company`, `material_request_type`,
`transaction_date`, `items`. Với quy trình mua hàng,
`material_request_type = Purchase`. Mỗi dòng lấy tối thiểu `item_code`, `qty`,
`uom`, `warehouse`, `schedule_date` và giữ lại `items[].name` để truy vết.

### 2.2. RFQ và Supplier Quotation

```text
POST /api/v1/crm/request-for-quotations
POST /api/v1/crm/supplier-quotations
```

RFQ phải giữ liên kết `items[].material_request` và
`items[].material_request_item`. Supplier Quotation phải giữ
`items[].request_for_quotation` và `items[].request_for_quotation_item`.

Contract hiện tại chưa công bố action submit/cancel cho RFQ và Supplier
Quotation. Vì vậy Portal chỉ dùng chúng làm nguồn lựa chọn và giá; không giả
định chúng đã có lifecycle API như PO.

### 2.3. Purchase Order sau approval

```text
POST /api/v1/buying/purchase-orders
POST /api/v1/buying/purchase-orders/{name}/submit
```

Payload PO phải có `supplier`, `company`, `transaction_date`, `schedule_date`,
`currency`, `conversion_rate` và `items`. Mỗi dòng phải giữ một nhóm liên kết
nguồn: `material_request` + `material_request_item`, hoặc
`supplier_quotation` + `supplier_quotation_item`.

## 3. Form Approval hoàn chỉnh

Approval definition: `Phê duyệt mua hàng` (`FED2698B-DBF9-4D38-97C1-25E59E8A2FA8`).

Schema review đang chạy trên tenant được cập nhật bằng Lark OpenAPI full
replacement (`POST /open-apis/approval/v4/approvals` với `approval_code` hiện
hữu). Form dùng locale mặc định kỹ thuật `zh-CN` nhưng toàn bộ giá trị dịch là
tiếng Việt để tương thích giới hạn locale của API tạo definition. Lark trả về
`custom_id` ổn định và có thể tự sinh `id` runtime mới; adapter phải map được cả
hai.

Các control thực tế trên Approval review:

| Control | Loại | Nội dung |
|---|---|---|
| `widget0` | textarea | Lý do mua hàng |
| `widget16000000000001` | input | Đường dẫn chi tiết; value là deep link chỉ đọc về PO Draft |
| `widget15754430770720001` | radioV2 | Loại mua hàng |
| `widget2` | date | Ngày cần giao hàng |
| `widget16000000000003` | textarea | Điều khoản thanh toán |
| `widget16000000000004` | textarea | Điều kiện giao hàng |
| `widget3` | fieldList | Chi tiết mua hàng; Lark tự tổng hợp số lượng/đơn giá/thành tiền trong bảng |
| `widget16000000000005` | amount trong fieldList | Thành tiền từng dòng, chỉ VND |
| `widget15828096955850001` | attachmentV2 | Tài liệu đính kèm |

Các field dưới đây là snapshot do Portal sinh ra tại thời điểm submit. Người
duyệt không sửa các giá trị này trong Approval; nếu PO Draft thay đổi, Portal
phải tạo attempt mới.

| ID | Nhãn | Loại Lark | Bắt buộc | Nguồn / quy tắc |
|---|---|---|---:|---|
| `po_draft_id` | PO Draft ID | Input | Có | Lark Base record ID; khóa truy vết |
| `approval_attempt` | Approval Attempt | Number | Có | Tăng tuần tự theo draft |
| `material_request_name` | Material Request | Input | Có | ERPNext MR `name` |
| `request_for_quotation_name` | Request for Quotation | Input | Không | ERPNext RFQ `name` |
| `supplier_quotation_name` | Supplier Quotation | Input | Không | Báo giá được chọn |
| `company` | Company | Input | Có | ERPNext `company` |
| `supplier` | Supplier | Input | Có | ERPNext Supplier `supplier` |
| `transaction_date` | Transaction Date | Date | Có | PO snapshot |
| `schedule_date` | Required By | Date | Có | PO snapshot; không sớm hơn transaction date |
| `currency` | Currency | Input | Có | ERPNext PO currency |
| `conversion_rate` | Conversion Rate | Number | Có | ERPNext PO conversion rate |
| `total_qty` | Total Quantity | Number | Có | Tổng từ item snapshot |
| `net_total` | Net Total | Amount/Number | Có | Tổng trước thuế/chi phí |
| `total_taxes` | Taxes | Amount/Number | Có | Tổng thuế |
| `grand_total` | Grand Total | Amount/Number | Có | Giá trị phê duyệt |
| `item_summary` | Items | Textarea | Có | Một dòng/item: mã, mô tả, qty, UOM, rate, amount, warehouse |
| `payment_terms` | Payment Terms | Textarea | Không | Điều khoản mua |
| `delivery_terms` | Delivery Terms | Textarea | Không | Điều kiện giao hàng |
| `justification` | Justification | Textarea | Có | Lý do chọn nhà cung cấp / mua hàng |
| `supporting_documents` | Supporting Documents | Attachment | Không | Báo giá, hợp đồng, tài liệu liên quan |
| `portal_url` | Open in Global Portal | Input/URL | Có | Deep link chỉ đọc về PO Draft |
| `snapshot_hash` | Snapshot Hash | Input | Có | SHA-256 canonical JSON; dùng kiểm tra bất biến |
| `source_updated_at` | Source Updated At | Date/Time text | Có | `last_modified` của Base snapshot |

`item_summary` phải được format ổn định, ví dụ:

```text
1. ITEM-001 | Laptop | qty=2 | UOM=Nos | rate=25000000 | amount=50000000 | WH-HN
2. ITEM-002 | Docking station | qty=2 | UOM=Nos | rate=3000000 | amount=6000000 | WH-HN
```

Dùng text snapshot cho item giúp form duyệt dễ đọc và tránh phụ thuộc vào
format phức tạp của child-table trong Approval API. Dữ liệu có cấu trúc đầy đủ
vẫn phải lưu ở Lark Base `PO Draft Item` và được Portal gửi sang ERPNext.

## 4. Process và quyền duyệt

Process tối thiểu:

```text
START -> Purchase Approval (Personal / nhóm được cấu hình) -> END
```

- Submitter là user Lark hiện hành do Portal xác định từ identity ổn định.
- Approver do definition quản lý, không nhận tùy ý từ browser.
- Có thể mở rộng thành nhiều node theo ngưỡng `grand_total`, nhưng không đưa
  điều kiện nhánh vào bản đầu vì Approval API tạo definition không hỗ trợ
  conditional branch đầy đủ.
- Comment khi approve/reject là dữ liệu audit; Portal phải đọc lại instance
  sau webhook để lấy trạng thái chính thức.

## 5. Trạng thái và giao dịch

Lark Base `PO Draft` nên có các field:

```text
draft_id
draft_status: Draft | Pending Approval | Approved | Rejected | Canceled |
              Sent to ERP | ERP Submitted | ERP Failed
approval_instance_code
approval_attempt
approval_status
payload_hash
approval_submitted_at
approval_completed_at
erp_purchase_order_name
erp_error
```

Luồng submit:

1. Portal đọc lại PO Draft và toàn bộ PO Draft Item từ Base.
2. Kiểm tra các liên kết MR/RFQ/Supplier Quotation, số lượng dương, supplier,
   company, currency, ngày và tổng tiền.
3. Canonicalize snapshot, tính `snapshot_hash`, ghi trạng thái
   `Pending Approval` và tạo Lark Approval instance.
4. Lưu `approval_instance_code` và `approval_attempt` bằng update có điều kiện;
   request lặp lại không tạo instance thứ hai.

Luồng approved:

1. Nhận event nhưng không tin event payload một mình; dedupe theo `event_id`.
2. Đọc lại Approval instance và xác nhận `APPROVED`.
3. Đọc lại Base Draft + Items; hash phải trùng `snapshot_hash` và draft phải
   còn đúng attempt.
4. Gọi endpoint ERPNext tạo PO với idempotency key ổn định.
5. Đọc lại PO; nếu policy yêu cầu chứng từ chính thức ngay thì gọi action
   submit, sau đó ghi `erp_purchase_order_name` và `ERP Submitted` về Base.

Nếu hash khác, từ chối phát hành PO, đánh dấu `ERP Failed`/`Approval Superseded`
và bắt buộc tạo attempt mới. Reject/cancel không gọi ERPNext.

## 6. Contract bổ sung đề xuất cho Global Portal

Các route này thuộc Portal, không thuộc browser của `apps/erp`:

```text
POST /api/integrations/lark/po-drafts/{draftId}/submit-approval
POST /api/integrations/lark/webhooks/approval
POST /api/integrations/lark/po-drafts/{draftId}/reconcile
```

`submit-approval` trả về `draft_id`, `approval_instance_code`, `attempt`,
`snapshot_hash`, `status`; không trả tenant token hay thông tin credential.

ERPNext nên có một route server-to-server riêng, ví dụ:

```text
POST /api/v1/buying/purchase-orders/from-approved-lark
```

Route này kiểm tra chữ ký nội bộ, `approval_instance_code`, `snapshot_hash`,
`approval_attempt`, quyền gọi và idempotency trước khi tạo PO. Không cho client
web gọi trực tiếp route này.

## 7. Kiểm tra chấp nhận

- MR tạo được và có `name`/child row names.
- RFQ liên kết đúng MR; Supplier Quotation liên kết đúng RFQ.
- Submit cùng một `draft_id` và attempt chỉ tạo một Approval instance.
- Approval instance chứa đúng snapshot và một task PENDING.
- Sửa Base sau submit không được tạo PO từ approval cũ.
- APPROVED hợp lệ tạo đúng một PO; retry không tạo PO thứ hai.
- REJECTED/CANCELED không tạo PO.
- PO tạo ra giữ được liên kết nguồn và metadata Lark.
- Mọi callback sai chữ ký, sai hash, sai attempt hoặc sai trạng thái đều bị từ
  chối và có log audit không chứa secret.

## 8. Căn cứ

- [ERPNext integration contract](../../contracts/erpnext-integration.yml)
- [Public OpenAPI contract](../../contracts/openapi/public.yaml)
- [Purchase accounting/API flow](../Purchase_Accounting_API_Flow.md)
- [Next.js purchase orchestration](../../apps/erp/src/lib/purchase-orchestration.ts)
- [Lark PO Draft ownership decision](Lark_PO_Draft_Approval.md)
- [Lark Approval create API](https://feishu.apifox.cn/api-9020746)
- [Lark Approval instance API](https://open.larksuite.com/document/server-docs/approval-v4/instance/create)
