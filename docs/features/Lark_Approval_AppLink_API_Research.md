# Lark Approval AppLink và Open API

## Kết luận

App Link đã được tạo cho Approval `LeTRON PO Draft Approval`:

```text
https://applink.larksuite.com/T99zWx8SX44l
```

Lark giải mã link này thành App Link nội bộ có `definition ID`:

```text
7683375394858372634
```

`definition ID` này không phải `approval_code`. Khi dùng nó với:

```text
GET /open-apis/approval/v4/approvals/{approval_code}
POST /open-apis/approval/v4/instances
```

Lark trả `1390002 approval code not found` hoặc `1390001 approval code not found`.

## Các kiểm chứng đã thực hiện

- App lấy được `tenant_access_token`.
- Lark Base đã tạo và đọc lại thành công.
- Quyền Approval đã hoạt động.
- Quyền Contacts đã hoạt động; email approver đã resolve được thành `open_id` và `union_id`.
- Native Approval definition API đã nhận đúng schema nhưng trả `1395001 record not found`.
- Approval list API dùng tenant token trả lỗi token vì endpoint này trả các definition mà current user có thể khởi tạo.
- App Link resolver chính thức của Lark trả về definition ID nhưng không trả `approval_code`.

## Boundary kiến trúc

Lark có hai định danh khác nhau:

```text
App Link / mini program: definition ID
Approval Open API: approval_code
```

Muốn Global Portal tạo Approval Instance, cần một trong hai nguồn:

1. `approval_code` lấy từ API tạo definition; hoặc
2. `approval_code` lấy từ Approval Admin URL / user-context API.

Tenant token hiện tại không đủ để đổi App Link definition ID thành approval code. Không nên suy diễn hoặc dùng definition ID thay cho approval code.

## Thiết kế được xác nhận

```text
Global Portal
  -> POST Approval Instance bằng approval_code
  -> nhận instance_code
  -> nhận/đọc status APPROVED
  -> gọi ERPNext tạo PO
```

ERPNext không tạo Draft và không tự quyết định approval state.

## Tài liệu tham chiếu

- Lark App Link resolver: `GET /open-apis/applink/longlink/v1/get?shortLink=...&businessTag=applink`.
- [Lark create approval definition](https://feishu.apifox.cn/api-9020746)
- [Lark list approval definitions](https://feishu.apifox.cn/api-59181909)
- [Lark SDK approval model](https://pkg.go.dev/github.com/larksuite/oapi-sdk-go/v3%40v3.9.10/service/approval/v4)
