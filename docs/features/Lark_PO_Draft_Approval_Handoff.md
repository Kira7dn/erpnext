# Handoff: MR/RFQ tới Lark PO Approval

## Trạng thái chính xác

Đã triển khai server-side handoff và đã acceptance live tới trạng thái Approval
đang chờ duyệt trên tenant thật. Runtime hiện dùng definition `Purchase`
(`FED2698B-DBF9-4D38-97C1-25E59E8A2FA8`) và map theo stable widget id/custom id
của form đã Việt hóa. Phần tạo Purchase Order chỉ chạy sau khi người duyệt
thao tác APPROVED và webhook hợp lệ được nhận.

Đã có:

- `apps/auth-server/src/server/lark-purchase.ts`: adapter server-side gọi Lark
  Base và Approval instance.
- `POST /api/integrations/lark/po-drafts/{draftId}/submit-approval`: route cần
  session của Global Portal.
- `POST /api/integrations/lark/webhooks/approval`: route nhận event, đọc lại
  Approval instance và có nhánh handoff APPROVED sang ERPNext.
- `apps/letron_api/letron_api/lark_po.py`: control-plane handler tạo và submit
  Purchase Order bằng native ERPNext controller.
- Contract đã đăng ký route ERPNext `from_approved`.
- `POST /api/integrations/lark/purchase-orchestrations/{id}/submit-approval`:
  Global Portal đọc lại MR/RFQ/Supplier Quotation qua Gateway và canonicalize
  PO Draft server-side.
- `LarkPoDraftState` và `LarkWebhookEvent`: state/idempotency/dedupe bền vững
  trong PostgreSQL; Redis lock chỉ dùng để serialize request ngắn hạn.
- ERPNext `purchase_schema.ensure_schema`: metadata Lark trên Purchase Order và
  correlation fields được tạo qua migration.
- `apps/erp` tạo tự động MR → RFQ → Lark Approval trong cùng orchestration; không
  cần Supplier Quotation và UI không còn nút gửi Approval thủ công.
- Native Approval definition `Purchase` đã được cập nhật bằng Lark OpenAPI qua
  `lark-cli api POST /open-apis/approval/v4/approvals` với chính
  `approval_code` hiện hữu (full replacement update), không tạo definition mới.
  Lark readback trả về definition ID `7683406313657503258`, status `ACTIVE`,
  viewer toàn tenant và node `Phê duyệt` vẫn giao `Lê Đức Anh`.
- Form review hiện có các trường tiếng Việt: `Lý do mua hàng`, `Thông tin tham
  chiếu ERP`, `Loại mua hàng`, `Ngày cần giao hàng`, `Điều khoản thanh toán`,
  `Điều kiện giao hàng`, `Chi tiết mua hàng` với từng dòng gồm
  `Tên hàng hóa`, `Quy cách / mô tả`, `Số lượng`, `Đơn giá`, `Thành tiền`, và
  `Tài liệu đính kèm`. Các control tiền tệ chỉ cho phép VND.

Chưa có:

- `LARK_EVENT_ENCRYPT_KEY` vẫn phải có trong runtime Auth trước khi acceptance
  phần webhook APPROVED → ERPNext PO.
- Phần giao diện chrome cố định của Lark Admin/Approval vẫn hiển thị theo ngôn ngữ
  tài khoản Lark; các nhãn, nội dung và node thuộc definition đã là tiếng Việt.
  Runtime mapper theo cả `custom_id` và tên tiếng Việt nên không phụ thuộc ID
  runtime mà Lark tự sinh sau khi cập nhật definition.
- Acceptance live phần MR → RFQ → Base → Approval đã đạt; chưa bấm APPROVED nên
  chưa có bằng chứng PO cuối chuỗi.

## Việc người tiếp theo phải làm

1. Giữ Approval definition dùng đúng `approval_code`
   `FED2698B-DBF9-4D38-97C1-25E59E8A2FA8`, không dùng App Link definition ID.
2. Chạy acceptance APPROVED bằng chính người duyệt `leducanh@ledb.vn`, sau đó
   kiểm tra webhook, PO readback và idempotency.
3. Bổ sung/giữ test live cho success, duplicate, rejected, canceled, hash
   mismatch, changed draft và ERP failure khi tenant/runtime sẵn sàng.

## Tiêu chí bàn giao đạt

Chỉ đánh dấu hoàn tất khi có bằng chứng cho cả chuỗi:

```text
MR created
  -> RFQ created
  -> exactly one Lark PO Draft (stable record ID)
  -> exactly one PENDING Approval instance
  -> APPROVED webhook/reconcile
  -> exactly one submitted ERPNext Purchase Order
```

Các trường hợp REJECTED/CANCELED, retry cùng correlation ID và sửa Base sau khi
submit cũng phải được kiểm thử; không chấp nhận chỉ kiểm tra HTTP 200 của một
route riêng lẻ.

## Kiểm tra hiện tại

- Auth Server `db:generate`, `typecheck`, `lint`, test handoff và build đã xanh;
  migration `202609090001_lark_po_handoff` đã áp dụng.
- ERP `typecheck` và Python compile của handler đã xanh.
- Launcher `-Action config` và reload đã chạy; sau bootstrap Frappe health trả
  HTTP 200 và config/policy không drift.
- Live evidence trước khi publish: `MAT-MR-2026-00013` → `RFQ-2026-00009` → Base
  draft `recvuHqIK9b5y7` → Approval instance
  `2D5E6F8B-720E-409F-B136-70505DFF65B9`, `PENDING`, một task PENDING giao đúng
  `leducanh@ledb.vn`.
- Live evidence sau khi publish form tiếng Việt: `MAT-MR-2026-00015` →
  `RFQ-2026-00011` → Base draft `recvuHvWkkrPhi` → Approval instance
  `4C764ED6-F6A5-4ABE-9E28-FDD1A137442E`, `PENDING`, một task PENDING giao đúng
  `leducanh@ledb.vn`; readback có 4 nhóm control, một item row và amount
  `1000 VND`. Form readback xác nhận các nhãn `Lý do mua hàng`, `Loại mua hàng`,
  `Ngày cần giao hàng`, `Chi tiết mua hàng`, `Tên hàng hóa`, `Quy cách / mô tả`,
  `Số lượng(đơn vị)`, `Đơn giá`.
- Live evidence nhiều Item/nhiều Supplier: `MAT-MR-2026-00016` có 2 item
  (`...-Item` qty 2, `...-Trace Item` qty 3) → `RFQ-2026-00012` có đúng 2 item
  và 2 Supplier (`...-Supplier`, `dsfsdfsdfd`) → Base draft `recvuHJcRzBL6b` →
  Approval instance `48789001-BE2D-4559-AF36-F47CE3C3939D`, `PENDING`, một task
  PENDING giao đúng `leducanh@ledb.vn`; Approval readback có đúng 2 item rows,
  amount VND riêng cho từng dòng.

## Tài liệu Lark đã dùng

- [Approval create/update API](https://open.larksuite.com/document/server-docs/approval-v4/approval/create)
- [Approval definition form-control parameters](https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/reference/approval-v4/approval/approval-definition-form-control-parameters)
- [Approval definition get API](https://open.larksuite.com/document/server-docs/approval-v4/approval/get)
