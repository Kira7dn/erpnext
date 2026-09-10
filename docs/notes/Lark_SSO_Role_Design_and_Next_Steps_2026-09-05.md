# Lark SSO và OpenAPI RBAC tập trung

- Ngày cập nhật: 2026-09-05
- Trạng thái: đã triển khai local; còn acceptance bằng session người dùng thật
- Phạm vi: Letron Global Portal và ERPNext nội bộ

## Phạm vi RBAC đã chốt

RBAC chỉ quản lý quyền gọi API theo ba thành phần:

```text
Lark User Group → OpenAPI resource → CRUD operation
```

Không triển khai trong scope này:

- multi-tenant authorization hoặc tenant selector;
- field-level permission, ẩn/hiện từng field;
- record-level/data scope theo Company, Warehouse hoặc người dùng;
- metadata-driven form generator hoặc schema editor trên Portal;
- Allow/Deny/Inherit, approval workflow, role bundle native ERPNext.

Company, Warehouse, workflow và business validation vẫn là dữ liệu/nghiệp vụ do
ERPNext xử lý. Chúng không tạo thêm một lớp RBAC trong Global Portal.

## Quyết định kiến trúc

Lark là Source of Truth cho User Group và membership. Mỗi Lark User Group là
một Role nghiệp vụ. Global Portal là control plane để cấp capability cho Role
từ OpenAPI contract. ERPNext nhận projection và vẫn enforce quyền trên từng
request.

```text
Lark User Group / membership
              |
              v
Global Portal OpenAPI RBAC policy
              |
              v
Next.js ERP UI + ERPNext permission projection
              |
              v
Global Gateway + ERPNext request enforcement
```

Không quản trị role permission bằng ERPNext UI. Không tạo Role theo từng người.
Không cho Portal bypass authorization của ERPNext.

## Source of Truth và ranh giới

| Dữ liệu | Source of Truth |
|---|---|
| User, trạng thái user, membership User Group | Lark |
| Role nghiệp vụ | Lark User Group |
| Capability CRUD trên OpenAPI resource | Global Portal |
| Endpoint/action nghiệp vụ | `contracts/openapi/public.json` |
| ERP application UI và feature navigation | Global Portal Next.js |
| ERP Role và native DocPerm projection | ERPNext, do Portal publish xuống |
| Authorization runtime | Global Portal gateway và ERPNext |
| Company, warehouse, workflow, data scope | ERPNext/native policy |

Lark App permission/scope chỉ cho phép app gọi Lark API; không phải ERP
permission. Portal chỉ cấp capability theo policy; UI visibility không phải
security boundary.

## Role hiện có

Portal query trực tiếp Lark Contact User Group catalog và render đúng group Lark
trả về. Không render role kỳ vọng và không tự tạo role thiếu.

Hiện local có:

- `ERP - Access`: required access group, quyết định user được vào ERP.
- `Global Access Admin`: được phép mở trang Role Permission Setting.

Nếu cần thêm nghiệp vụ, tạo User Group trong Lark trước. Khi Portal không nhận
được group, phải báo lỗi catalog; không thay thế bằng role giả.

## Mô hình capability CRUD

Policy và UI chỉ sử dụng:

```text
list, read, create, update, delete
```

OpenAPI action vẫn giữ endpoint riêng nhưng được chuẩn hóa khi authorization:

| Endpoint/API action | Capability Portal |
|---|---|
| GET collection | `list` |
| GET record | `read` |
| POST collection | `create` |
| PUT/PATCH record | `update` |
| POST `submit` | `update` |
| POST `reconcile` | `update` |
| POST `unreconcile` | `update` |
| DELETE record | `delete` |
| POST `cancel` | `delete` |

Đây là mô hình quyền nội bộ cố ý đơn giản hóa: `update` cho phép lifecycle
action submit/reconcile/unreconcile; `delete` cho phép cancel và DELETE.
ERPNext vẫn thực hiện native validation, reversal, ledger và workflow.

## UI Role Permission Setting

Trang quản trị nằm tại `/admin/access-policy` và chỉ dành cho Global Access
Admin.

- Một RBAC table duy nhất.
- Mỗi Lark User Group là một hàng chính.
- Nút expand/collapse hiển thị các OpenAPI resource đã chọn.
- Mỗi resource là sub-row.
- Chỉ có checkbox cho năm capability CRUD.
- Nút `+` duy nhất nằm cạnh User Group.
- Nút `+` mở modal multi-select resource từ OpenAPI catalog.
- Không có tạo Role thủ công, cột Resource riêng, Sync, Save, Allow/Deny/Inherit.
- Thay đổi checkbox hoặc thêm resource tự động lưu.

Catalog đọc từ `contracts/openapi/public.json`, loại endpoint không public và
gộp action vào capability CRUD. Resource không có operation tương ứng hiển thị
`—`.

## Autosave và publish

Mỗi thay đổi UI debounce 500ms. Client giữ policy pending và chỉ gửi một POST tại
một thời điểm; thay đổi mới nhất được gửi sau request trước. Lỗi 5xx retry tối
đa ba lần với backoff ngắn và hiển thị toaster.

Backend validate policy, tính canonical SHA-256, dùng PostgreSQL advisory
transaction lock để serialize request/tab đồng thời, cấp version duy nhất,
publish ERPNext, supersede policy trước đó và ghi audit.

Không có approve/draft workflow trong UI và không yêu cầu người dùng bấm Save.

## ERPNext projection

Portal gửi policy đã validate tới `letron_api.control.access_policy.publish`. ERPNext:

- chỉ tạo/cập nhật role có prefix `Letron Policy - `;
- không quản lý `Administrator`, `System Manager`, `All`, `Guest`;
- map CRUD vào native read/create/write/delete;
- map `update` thêm native submit chỉ với resource có action submit trong route;
- map `delete` thêm native cancel chỉ với resource có action cancel trong route;
- giữ native controller cho submit, cancel, reconcile và unreconcile;
- xóa Custom DocPerm managed bị stale và clear cache.

ERPNext không được dùng để chỉnh trực tiếp managed permission. Native
`/api/resource` và `/api/method` business routes bị chặn với user SSO; chỉ
request `/api/v1` có chữ ký Gateway được phép đi qua. Mapping cũ
`Lark group -> ERP native role` không còn cấp role nghiệp vụ; login chỉ dùng
Lark để xác nhận access và gỡ các role legacy đã được cấu hình. Role nghiệp vụ
chỉ được cấp từ policy CRUD đã publish qua Gateway dưới prefix
`Letron Policy - `. Drift phải được phát hiện và xử lý fail-closed.

Portal refresh membership Lark khi snapshot quá `AUTH_GROUP_SYNC_STALE_SECONDS`.
Nếu không xác nhận được membership mới, Portal không authorize session hiện tại.
Policy publish đối chiếu mọi group ID và required access group với Lark User Group
catalog hiện tại; group không tồn tại bị từ chối.

## Homepage Global Portal

Homepage không dùng mapping visibility thứ hai:

- Card `Letron ERP` hiển thị khi user thuộc policy `requiredAccessGroupId`, tức
  `ERP - Access`.
- Các feature bên trong card được suy ra từ CRUD policy đã published.
- Card `Role Permission Setting` chỉ hiển thị khi user thuộc `Global Access
  Admin`.
- User không có required access group không được thấy card ERP.
- Ẩn card chỉ là presentation; gateway và ERPNext vẫn authorize request.

## Thay thế ERPNext UI bằng Next.js

Global Portal Next.js sẽ là UI duy nhất cho toàn bộ feature ERP được công bố
trong OpenAPI contract. ERPNext chỉ giữ backend, native controller, ledger,
workflow và enforcement; người dùng Lark không sử dụng ERPNext Desk để thao tác
nghiệp vụ.

Nguyên tắc render:

- Mỗi feature UI có một `module/resource` tương ứng trong
  `contracts/openapi/public.json`.
- Portal lấy published policy hiện tại và tính capability của user từ toàn bộ
  Lark User Group membership; quyền là phép hợp của các group user đang thuộc.
- Navigation, card, menu, route và action button chỉ được render khi policy cấp
  đúng capability. `list` cho collection view, `read` cho detail view,
  `create` cho nút tạo, `update` cho edit và lifecycle update, `delete` cho
  delete/cancel.
- Không render feature “dự kiến”, không hard-code role Finance/Warehouse/Sales,
  không tạo visibility mapping riêng trong Next.js. Feature chỉ xuất hiện khi
  resource và operation tồn tại trong OpenAPI catalog và được policy cấp.
- Khi policy hoặc membership thay đổi, Portal phải revalidate session/policy
  trước khi render route; trạng thái không xác định thì ẩn feature và hiển thị
  lỗi quyền rõ ràng.
- UI không được tự quyết định authorization. Mọi request từ Next.js đi qua
  Global Gateway, gateway kiểm tra lại published policy, sau đó ERPNext kiểm tra
  native permission và business validation.

Kế hoạch triển khai theo feature:

1. Sinh static resource/operation registry từ `contracts/openapi/public.json`,
   dùng chung cho navigation, route guard, page loader và action button. Registry
   chỉ cần module, resource, operation, path và operationId; không sinh metadata
   DocType hoặc form động.
2. Tạo từng Next.js page/module theo resource OpenAPI; request và response dùng
   schema đã có trong contract, còn layout/form được viết tĩnh theo feature.
   Page chỉ gọi Gateway bằng route đã đăng ký, không gọi `/api/resource` hoặc
   `/api/method` trực tiếp.
3. Áp dụng cùng một capability resolver cho server component, client control
   và API request preparation; không kiểm tra bằng tên ERP Role.
4. Với mỗi feature, kiểm chứng ma trận `Lark Group → resource → operation → UI`
   ở cả trạng thái được cấp và bị thu hồi, gồm refresh session và direct URL.
   Không cần kiểm thử tenant isolation, field visibility hoặc data scope.
5. Chỉ retire từng ERPNext Desk feature sau khi page Next.js tương ứng có đủ
   list/read/create/update/delete, error state, loading state và authorization
   acceptance.

Acceptance bắt buộc cho UI Next.js:

- User chỉ thấy đúng resource được cấp trong policy; resource chưa cấp không có
  trong navigation, không truy cập được bằng direct URL và không có action button.
- Từng checkbox CRUD trong Role Permission Setting tạo đúng thay đổi UI sau
  autosave và sau refresh.
- `list`, `read`, `create`, `update`, `delete` được kiểm thử độc lập trên cả UI
  và Gateway; submit/reconcile/unreconcile chỉ là hành vi backend được map vào
  `update`, cancel được map vào `delete`.
- User thuộc nhiều group thấy phép hợp quyền; khi bị gỡ required access group,
  toàn bộ ERP feature biến mất và request cũ bị từ chối.
- Không có feature nào được render chỉ vì user có native ERP role hoặc biết URL.

## Database và migration

Runtime dùng Neon serverless driver với pooled `DATABASE_URL`. Prisma Schema
Engine TCP không hoạt động ổn định trên môi trường Windows hiện tại, dù runtime
query được PostgreSQL.

`npm run db:migrate` dùng `scripts/migrate-neon.ts`, chạy migration files qua
Neon Client với thứ tự, checksum, transaction, advisory lock, bảng
`_prisma_migrations` và idempotency. Không in connection string, password hoặc
token vào log.

Migration CRUD policy và migration dọn legacy RBAC đã được apply; policy legacy đã normalize và không còn
operation `submit`, `cancel`, `reconcile`, `unreconcile` trong policy data.

Sau mỗi thay đổi `apps/auth-server/prisma/schema.prisma`, phải chạy
`npm run db:generate`, `npm run db:migrate`, `npm run check` rồi restart
`npm run dev`. Prisma Client được generate vào `generated/prisma`; Next.js dev
server giữ module đã load trong memory nên chỉ generate mà không restart có thể
gây lỗi `column does not exist` trên homepage hoặc `getPublishedPolicy()`.

## Cấu hình bảo mật

Secret thật và group ID thật chỉ nằm trong `.env` bị Git ignore. Tài liệu chỉ
dùng placeholder:

```env
GLOBAL_ACCESS_ADMIN_GROUP_ID=replace-with-lark-group-id
LETRON_SSO_REQUIRED_LARK_GROUP_ID=replace-with-erp-access-group-id
```

Stable identity bắt buộc là `lark + tenant_key + union_id`; không fallback sang
`open_id` và không tự liên kết chỉ vì trùng email.

## Kiểm chứng hiện tại

- Lark catalog trả về đúng 2 User Group local.
- Database có đầy đủ migration đến `202609050004_remove_legacy_rbac`.
- Policy published đã chuyển sang CRUD capability.
- Neon driver query `SELECT 1` pass.
- `/api/health` trả HTTP 200.
- `npm run check` pass: Prisma validate, TypeScript, ESLint, 19 tests và build.
- Homepage, error page và RBAC page dùng Tailwind thuần.
- Còn cần acceptance bằng browser session Lark thật sau khi refresh session và
  kiểm tra direct native ERP route bị chặn với user SSO.

## Checklist acceptance

1. Chỉ `ERP - Access` thấy card ERP, không thấy admin card.
2. Chỉ `Global Access Admin` thấy admin card, không tự có ERP.
3. Thuộc cả hai group thấy cả hai card.
4. Thêm resource trong modal làm xuất hiện sub-row và tự lưu.
5. Tick CRUD checkbox tự lưu; refresh vẫn giữ quyền.
6. `update` authorize PUT/PATCH và submit/reconcile/unreconcile.
7. `delete` authorize DELETE và cancel.
8. Thiếu required access group bị gateway/ERP từ chối.
9. Hai autosave đồng thời không tạo duplicate version hoặc deadlock.
10. Policy publish và ERP projection readback khớp nhau.
