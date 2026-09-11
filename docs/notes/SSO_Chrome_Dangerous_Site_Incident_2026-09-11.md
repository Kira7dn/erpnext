# SSO Chrome Dangerous Site Incident — 2026-09-11

## Phạm vi

Note này ghi nhận hiện tượng Chrome hiển thị cảnh báo **Dangerous Site** khi
người dùng truy cập URL bắt đầu đăng nhập:

```text
https://auth.letron.vn/api/auth/start?return_to=/
```

Hiện tượng này phải được phân biệt với lỗi server `303 →
/error?code=login_start_failed` và lỗi `401` của script `real-test-mr.ts`.

## Hiện tượng quan sát được

Trong Chrome người dùng, trang cảnh báo hiển thị:

```text
Dangerous site
Attackers on the site you tried visiting might trick you into installing
software or revealing things like your passwords, phone, or credit card numbers.
```

Trong DevTools của lần xảy ra lỗi chỉ thấy URL request và referrer policy,
không có status code, response headers hoặc `Location`. Điều này phù hợp với
việc browser chặn tại lớp interstitial trước khi request hoàn tất.

## Bằng chứng runtime

- Playwright mở được `https://auth.letron.vn/`, nhưng flow server đi tới
  `/error?code=login_start_failed`; Playwright không tái hiện Chrome
  Safe-Browsing interstitial.
- Gọi bằng curl tới `/api/auth/start?return_to=/` nhận:

  ```text
  HTTP/1.1 303 See Other
  Location: /error?code=login_start_failed
  ```

- Đây là response của một lần gọi không qua Chrome; nó chứng minh Auth có một
  lỗi server riêng, không chứng minh browser block tạo ra `303`.
- Vercel production logs ghi nhận các request tới `/`, `/login`,
  `/api/auth/start` và `/api/auth/lark/start`, nhưng không có exception chi tiết
  vì handler hiện tại bắt lỗi và trả mã tổng quát.
- Audit production trước đó đã ghi nhận Dangerous Site tại route Lark cũ trước
  remediation. Vì vậy chưa có bằng chứng cho thấy thay đổi BFF là nguyên nhân
  bắt đầu của cảnh báo này.

## Kết luận tạm thời

Đối với màn hình người dùng đang thấy, blocker trực tiếp là Chrome/browser
block trước khi Auth xử lý xong request. Không được dùng `303`, migration hoặc
`real-test 401` để kết luận chúng là nguyên nhân của Dangerous Site.

Hiện chưa xác định được Chrome đánh dấu do:

1. reputation của hostname `auth.letron.vn`;
2. reputation của URL `/api/auth/start` hoặc redirect chain;
3. Chrome profile/extension/chính sách doanh nghiệp; hoặc
4. một tín hiệu khác trong Safe Browsing.

## Các vấn đề cần tách riêng

### A. Browser block — blocker người dùng

Phải kiểm tra bằng Chrome thật, clean profile, Incognito, thiết bị/mạng khác,
Chrome policy/extension và Google Safe Browsing/Search Console. Playwright
không đủ để đóng issue này vì không tái hiện được interstitial.

### B. Auth server fallback — lỗi server riêng

`apps/auth-server/pages/api/auth/lark/start.ts` bắt mọi exception và redirect
`303` tới `/error?code=login_start_failed`. Cần lấy sanitized exception và
request ID để xác định nguyên nhân gốc; không được suy đoán migration/database
khi chưa có log hoặc readback schema.

### C. Production real-test contract — lỗi test riêng

`scripts/real-test-mr.ts` gọi `/api/internal/test-session` và trước đây gửi
cookie Auth `letron_sso` trực tiếp sang ERP. Sau khi chuyển sang app-scoped
session, ERP BFF yêu cầu cookie tương ứng như
`__Host-letron_purchase_session`; đồng thời `gatewayRequest()` phải suy ra
`purchase` cho các namespace nghiệp vụ `/api/v1/stock`, `/api/v1/crm`,
`/api/v1/buying` và `/api/v1/files`. Hai điểm lệch contract này gây `401` trong
real-test, không phải bằng chứng cho Dangerous Site. Đã sửa và production
real-test đã pass.

## Test để đóng issue

1. Chrome thật: ghi nhận interstitial có xuất hiện ở clean profile hay không.
2. Chrome DevTools Network: xác nhận request có nhận status/response hay bị
   block trước HTTP.
3. So sánh Chrome, Edge/Firefox, Incognito, thiết bị và mạng khác.
4. Kiểm tra hostname và URL trên Google Safe Browsing Transparency Report;
   kiểm tra Security Issues/Search Console và yêu cầu review nếu bị đánh dấu.
5. Tạm thời bổ sung sanitized runtime logging cho Auth start, gọi lại endpoint,
   rồi xác định exception `login_start_failed` độc lập với browser block.

## Trạng thái

```text
Browser Dangerous Site: OPEN — chưa xác định nguồn đánh dấu
Auth 303 login_start_failed: OPEN — exception gốc bị handler che
real-test 401: RESOLVED — runner và gateway đã đồng bộ purchase app session;
production full real-test pass ngày 2026-09-11
```
