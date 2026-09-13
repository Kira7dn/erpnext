# Stock Features — Frontend Design

## 1. Mục tiêu và phạm vi

Tài liệu này mô tả thiết kế frontend Next.js cho route `/stock` theo sơ đồ
`Screen WH-01` và `Screen WH-02`, trong đó WH-02 là bước tiếp nhận hàng sau khi
Purchase Order đã được phê duyệt và Supplier giao hàng.

Phạm vi tối thiểu gồm:

```text
/stock
├── /warehouses       WH-01 — Warehouse
└── /receipts         WH-02 — Purchase Receipt
```

Frontend gọi các official public API đã có trong OpenAPI contract. Không tạo
API nghiệp vụ mới trong ERPNext và không coi việc ẩn button là cơ chế
authorization; quyền vẫn được kiểm tra ở Global Portal/Gateway và ERPNext.

Tài liệu này là design/spec. Tại thời điểm viết, frontend chưa có `src/app/stock`
và chưa có UI `/stock`; backend contract và một phần BFF proxy đã tồn tại.

## 2. Luồng nghiệp vụ

```mermaid
flowchart TD
    PO[Purchase Order Submitted] --> SUP[Supplier giao hàng]
    WH1[WH-01 Warehouse] -->|Warehouse reference| WH[Warehouse]
    SUP --> WH2[WH-02 Nhập nhận hàng]
    WH --> WH2
    WH2 -->|POST /api/v1/stock/purchase-receipts| PR[Purchase Receipt Draft]
    PR -->|supplier_delivery_note + items| PRD[Thông tin giao hàng đã nhập]
    PRD -->|POST /{name}/submit| SUB[Purchase Receipt Submitted]
    SUB -->|email invoice request| MAIL[Email tới Supplier]
    MAIL --> INV[Supplier nhập/upload Invoice]
    SUB -->|POST /{name}/cancel| CAN[Cancelled]
```

Warehouse là dữ liệu tham chiếu cho các field kho trong Purchase Receipt. Tạo
Warehouse không tự động tạo Purchase Receipt. Người dùng chỉ lập WH-02 sau khi
PO đã ở trạng thái Submitted và hàng thực tế đã được Supplier giao tới.

`supplier_delivery_note` là số/chứng từ giao hàng do Supplier cung cấp; đây là
field trên Purchase Receipt, không phải ERPNext Sales Delivery Note.

## 3. Route map

| Màn hình | Next.js route | Mục đích |
|---|---|---|
| Stock home | `/stock` | Điều hướng tới Warehouse và Purchase Receipt |
| Warehouse list | `/stock/warehouses` | Danh sách, tìm kiếm, lọc, phân trang |
| Warehouse new | `/stock/warehouses/new` | Tạo Warehouse |
| Warehouse detail | `/stock/warehouses/[name]` | Xem chi tiết và trạng thái |
| Warehouse edit | `/stock/warehouses/[name]/edit` | Sửa Warehouse |
| Receipt list | `/stock/receipts` | Danh sách Purchase Receipt |
| Receipt new | `/stock/receipts/new` | Tạo phiếu nhận hàng Draft |
| Receipt detail | `/stock/receipts/[name]` | Xem phiếu và lifecycle actions |
| Receipt edit | `/stock/receipts/[name]/edit` | Sửa phiếu khi còn Draft |

Tên `receipts` là alias UI ngắn cho resource backend
`purchase-receipts`; không đổi tên resource trong API.

## 4. WH-01 — Warehouse

### UI behavior

- List hiển thị tối thiểu: `name`, `warehouse_name`, `company`, `parent_warehouse`,
  `warehouse_type`, `is_group` và `disabled`.
- Có search/filter server-side và pagination bằng `limit_page_length` và
  `limit_start`.
- Detail hiển thị các field được API trả về; field hệ thống hoặc HTML chỉ hiển
  thị read-only khi cần.
- Form tạo/sửa tối thiểu cần `warehouse_name` và `company`.
- Có thể chọn `parent_warehouse` từ danh sách Warehouse.
- `disabled` và `is_group` dùng checkbox hoặc control tương đương boolean.
- Không cho sửa Warehouse nếu backend trả về lỗi permission hoặc trạng thái
  không cho phép.

### API mapping

| UI action | Method | Official API |
|---|---|---|
| List Warehouse | GET | `/api/v1/stock/warehouses` |
| Detail Warehouse | GET | `/api/v1/stock/warehouses/{name}` |
| Create Warehouse | POST | `/api/v1/stock/warehouses` |
| Update Warehouse | PUT | `/api/v1/stock/warehouses/{name}` |
| Delete Warehouse | DELETE | `/api/v1/stock/warehouses/{name}` |

Delete chỉ được hiển thị nếu policy và backend cho phép. UI phải có confirmation
và không dùng delete để thay thế `disabled` trong nghiệp vụ thông thường.

## 5. WH-02 — Purchase Receipt

### UI behavior

- List hiển thị tối thiểu: `name`, `supplier`, `posting_date`, `company`,
  `set_warehouse`, `status` hoặc `docstatus`, và tổng quan số dòng hàng.
- Detail hiển thị header, các dòng `items`, warehouse, số lượng, UOM, rate và
  các reference Purchase Order nếu có.
- Form tạo Draft cần các field header bắt buộc theo generated contract:
  `naming_series`, `supplier`, `posting_date`, `posting_time`, `company`,
  `currency`, `conversion_rate` và `items`. Field `supplier_delivery_note` phải
  được nhập khi Supplier đã giao hàng và phải được hiển thị rõ trong form.
- Purchase Receipt phải tham chiếu tới Purchase Order đã Submit khi receipt
  được tạo từ PO; mỗi dòng giữ `purchase_order` và `purchase_order_item`.
- Child table `items` phải hỗ trợ thêm/xóa nhiều dòng; mỗi dòng cần giữ các
  reference native như `item_code`, `qty`, `uom`, `stock_uom`, `conversion_factor`,
  `warehouse`, `rate`, `purchase_order` và `purchase_order_item` khi có.
- Warehouse trong dòng hàng phải chọn từ Warehouse resource; không cho nhập
  tùy ý nếu field là Link tới Warehouse.
- Chỉ cho sửa khi chứng từ còn Draft. Submit và Cancel phải có confirmation.
- Chỉ gửi invoice request sau khi Submit Purchase Receipt thành công. Tạo Draft
  hoặc lưu `supplier_delivery_note` chưa được gửi email.
- Sau Submit, UI refresh detail/list và hiển thị trạng thái mới; không tự suy
  đoán trạng thái từ HTTP 200.
- Sau khi email được gửi, UI hiển thị trạng thái đã đề nghị Supplier nhập Invoice
  và cho phép tra cứu lại Receipt; không tự tạo Purchase Invoice ở frontend.
- Cancel chỉ dành cho chứng từ đã Submitted và phải hiển thị kết quả backend.

### API mapping

| UI action | Method | Official API |
|---|---|---|
| List Purchase Receipt | GET | `/api/v1/stock/purchase-receipts` |
| Detail Purchase Receipt | GET | `/api/v1/stock/purchase-receipts/{name}` |
| Create Draft | POST | `/api/v1/stock/purchase-receipts` |
| Update Draft | PUT | `/api/v1/stock/purchase-receipts/{name}` |
| Submit | POST | `/api/v1/stock/purchase-receipts/{name}/submit` |
| Cancel | POST | `/api/v1/stock/purchase-receipts/{name}/cancel` |
| Delete Draft | DELETE | `/api/v1/stock/purchase-receipts/{name}` |

Payload Purchase Receipt phải được validate bằng generated request contract
`createPurchaseReceiptRequestSchema`/`updatePurchaseReceiptRequestSchema`. Không
duy trì một validator thủ công thứ hai có thể lệch với generated contract.

### Handoff sau khi Submit

Sau khi `POST /{name}/submit` thành công, BFF hiện đăng ký Warehouse Receipt và
gửi email idempotent tới Supplier. Email có subject dạng
`Letron invoice request for {receiptName}` và hướng Supplier vào Supplier Portal
để nhập/upload Purchase Invoice. Nếu gửi email thất bại, frontend phải hiển thị
đây là lỗi hậu xử lý của Receipt đã Submit; không retry tạo lại Receipt.

Flow tương ứng trong runtime là:

```text
Purchase Receipt Submit
  -> registerWarehouseReceipt(receiptName)
  -> buildInvoiceRequestMail(...)
  -> sendSupplierPortalMail(...)
  -> Supplier XML Invoice / Purchase Invoice
```

## 6. BFF và generated contract

Có thể triển khai một proxy riêng:

```text
GET/POST/PUT/DELETE /api/stock/{resource}
    -> /api/gateway/api/v1/stock/{resource}
```

Hoặc mở rộng BFF resource đã có nếu giữ được các invariant sau:

- resource không nằm trong generated/public catalog thì trả `404`;
- chỉ forward method được phép;
- forward app session và authorization qua Gateway;
- giữ nguyên query `fields`, `filters`, `order_by`, `limit_page_length`,
  `limit_start`;
- không log cookie, token, secret hoặc raw credential;
- lỗi `401`, `403`, `409`, `417`, `429`, `502/503` được chuyển thành thông báo
  public phù hợp;
- response được kiểm tra bằng generated response contract ở server boundary.

Không thêm một route map thủ công thứ hai chỉ dành cho `/stock`. Resource
metadata và public-operation catalog phải tiếp tục dùng nguồn generated chung
cho Letron API, Global Auth và Next.js.

## 7. Component đề xuất

```text
src/app/stock/page.tsx
src/app/stock/layout.tsx
src/app/stock/warehouses/page.tsx
src/app/stock/warehouses/new/page.tsx
src/app/stock/warehouses/[name]/page.tsx
src/app/stock/warehouses/[name]/edit/page.tsx
src/app/stock/receipts/page.tsx
src/app/stock/receipts/new/page.tsx
src/app/stock/receipts/[name]/page.tsx
src/app/stock/receipts/[name]/edit/page.tsx

src/components/stock-resource-table.tsx
src/components/warehouse-form.tsx
src/components/purchase-receipt-form.tsx
src/components/purchase-receipt-items.tsx
src/components/stock-lifecycle-actions.tsx
```

`Warehouse` có thể dùng generic resource table/form. `Purchase Receipt` cần
component form riêng vì có child table, PO references,
`supplier_delivery_note` và lifecycle; không nên ép vào form CRUD phẳng đang
dùng cho accounting resource. Component này cũng cần hiển thị trạng thái
handoff invoice sau Submit.

## 8. Error, loading và permission

- Loading: skeleton cho list, detail và child table.
- Empty: nêu rõ API không có bản ghi, kèm nút refresh.
- `401`: chuyển về Lark login và giữ `returnTo`.
- `403`: hiển thị chưa được cấp quyền, không hiện form thao tác.
- `409`/`417`: hiển thị lỗi nghiệp vụ/validation từ API ở mức public-safe.
- `502`/`503`: hiển thị Gateway unavailable và nút retry.
- Disable nút trong lúc mutation để tránh double-submit.
- Sau mutation thành công, invalidate list query và reload detail từ API.
- Không coi response HTTP 200 đơn lẻ là bằng chứng Submit đã tạo stock/GL;
  acceptance phải đọc lại Purchase Receipt và trạng thái backend.

## 9. Acceptance criteria

- [ ] `/stock` mở được và navigation active đúng cho nested route.
- [ ] WH-01 list/detail/create/edit gọi đúng Warehouse endpoint.
- [ ] WH-01 chọn được `parent_warehouse` từ dữ liệu API.
- [ ] WH-02 list/detail/create/edit gọi đúng Purchase Receipt endpoint.
- [ ] WH-02 chỉ cho tạo Receipt từ Purchase Order đã Submitted và hàng đã được
      xác nhận là đã giao.
- [ ] Nhập và lưu đúng `supplier_delivery_note` do Supplier cung cấp.
- [ ] Child table giữ đúng item, qty, UOM, warehouse và native references.
- [ ] Draft có thể sửa; Submit và Cancel có confirmation và read-back trạng thái.
- [ ] Chỉ sau Submit mới phát sinh invoice request email tới đúng Supplier.
- [ ] Không tạo lại Receipt khi email gửi thất bại; có retry handoff an toàn.
- [ ] Không có endpoint ngoài generated/public contract.
- [ ] `401`, `403`, validation, conflict và Gateway unavailable có UI rõ ràng.
- [ ] Typecheck, lint, build và `git diff --check` đạt.
- [ ] Browser verification mở `/stock`, tạo/sửa dữ liệu test và xác nhận detail
  read-back từ runtime.
- [ ] Runtime acceptance nếu tạo chứng từ thật phải có dữ liệu test được xác
  định và cleanup/rollback rõ ràng; không dùng static contract test thay thế.
- [ ] Browser acceptance xác nhận email invoice request và Supplier Portal nhận
  đúng Receipt sau khi WH-02 Submit.

## 10. Trạng thái triển khai

`DESIGN_ONLY` — tài liệu đã mô tả route và mapping API; frontend `/stock` chưa
được triển khai hoặc runtime-verified. `real-test-production.ts` đã có backend
flow tương ứng tới Purchase Receipt Submit, email invoice request và Supplier
Invoice, nhưng chưa phải browser acceptance cho `/stock`.

### Nguồn đối chiếu

- Ảnh thiết kế WH-01/WH-02 do người dùng cung cấp.
- `contracts/generated/openapi/modules/stock.yaml`.
- `contracts/openapi/public.json`.
- `apps/erp/src/generated/zod.ts`.
- `apps/erp/src/app/api/purchase/[...path]/route.ts`.
- `scripts/real-test-production.ts` và `scripts/real-test-mr.ts`.
