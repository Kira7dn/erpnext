# ERPNext Frontend Reference

Đây là bản sao tham chiếu các client script và DocType metadata của ERPNext
được lấy từ container `erpnext-backend-1` ngày 2026-09-08.

## Files

- `buying/supplier/supplier.js` và `supplier.json`: Supplier form, Contact,
  Address, query và các field liên quan.
- `stock/item/item.js` và `item.json`: Item form, field và behavior của Item.
- `stock/material_request/material_request.js` và `material_request.json`:
  Material Request, child items, query, status và Create actions.
- `public/js/contact.js` và `public/js/address.js`: behavior dùng chung cho
  Contact/Address.

## Cách dùng

Đây chỉ là reference để đối chiếu field và behavior khi xây FE Letron. Không
import các file này vào Next.js runtime và không gọi các method Frappe trong
source reference. FE Letron phải gọi official public API đã được expose trong
OpenAPI contract.

Purchase FE vẫn giữ ba screen:

```text
PUR-01 Supplier → PUR-02 Material → PUR-03 Material Request → Lark Endpoint
```

`Create RFQ` là action trong PUR-03, dùng Supplier người dùng đã chọn; không
tạo RFQ management screen riêng.
