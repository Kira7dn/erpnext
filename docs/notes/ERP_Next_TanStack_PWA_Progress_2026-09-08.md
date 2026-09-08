# ERP Next.js, TanStack Query và PWA — tiến độ 2026-09-08

## Trạng thái

Đã triển khai trên `main` và đã push:

- `3f7a620ee5` — hoàn tất chuyển các client request còn lại sang TanStack Query.
- `9f88b6c8f3` — thêm PWA nhẹ dùng manifest/icon chung.
- `fb5d0274c8` — tách manifest Accounting và Assets; commit này sau đó được
  sửa route manifest trong `8075afcae6`.
- `8075afcae6` — expose đúng các manifest riêng qua Route Handler.

## TanStack Query

Đã hoàn thành phạm vi client data layer:

- `QueryProvider` dùng `staleTime` 15 giây, `gcTime` 5 phút và retry có giới
  hạn theo HTTP status.
- Các query/mutation client đi qua `clientQuery`, không gọi `fetch` trực tiếp
  trong component.
- Accounts Settings, Statement Import, Bank Reconciliation, native reports,
  record form/action và asset action/lifecycle đã dùng query/mutation.
- Mutation có invalidation theo resource để tránh hiển thị dữ liệu cũ sau
  thay đổi.
- Sidebar đã tắt prefetch toàn bộ link; việc này không sửa được redirect của
  Lark và có thể làm thời gian chờ navigation dễ thấy hơn. Đây là điểm cần
  đánh giá riêng nếu tối ưu navigation tiếp.

## PWA nhẹ

Đã triển khai, không có service worker và không cache API:

| PWA | Manifest | `id` | `start_url` | `scope` |
|---|---|---|---|---|
| LeTRON-Kế toán | `/accounts/manifest.webmanifest` | `/accounts` | `/accounts` | `/accounts` |
| LeTRON-Tài sản | `/assets/manifest.webmanifest` | `/assets` | `/assets` | `/assets` |

Mỗi phân hệ có icon SVG riêng. Root `/manifest.webmanifest` vẫn giữ cho
`LeTRON-ERP` tổng quát. Proxy cho phép manifest/icon public để browser có thể
đọc metadata cài đặt mà không cần session.

PWA không thay đổi Lark Web App name, cookie SSO, redirect Auth hoặc độ trễ
Gateway/ERPNext. PWA chỉ cung cấp install metadata và standalone display khi
người dùng cài từ browser.

## Kiểm chứng

- `npm run typecheck`: pass.
- `npm run lint`: pass.
- `npm run build`: pass; build sinh `/accounts/manifest.webmanifest` và
  `/assets/manifest.webmanifest`.
- Production trả `200 application/json` cho cả hai manifest sau deployment
  `Ready`.
- Không stage các screenshot untracked trong root.

Chưa coi việc cài đặt PWA trên từng browser/device là runtime acceptance. Cần
kiểm tra thủ công nếu muốn xác nhận install prompt, icon hiển thị và hành vi
standalone trên Chrome desktop/mobile.
