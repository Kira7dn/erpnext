# Letron SSO architecture remediation design

## 1. Quyết định kiến trúc

Phương án triệt để là tách session của Auth Server khỏi session của ERP bằng
Backend-for-Frontend (BFF) session exchange:

~~~text
Browser -- host-only ERP cookie --> ERP BFF (erp.letron.vn)
ERP BFF -- OIDC authorization-code exchange --> Auth Server (auth.letron.vn)
Auth Server -- upstream authentication --> Lark
ERP BFF -- short-lived signed assertion --> ERPNext API
~~~

Browser không còn phải gửi cookie của Auth sang ERP. Auth Server vẫn là nguồn
identity, group membership và policy; ERP BFF chỉ sở hữu session boundary của
ứng dụng ERP.

Đây là phương án nên chọn vì xử lý nguyên nhân gốc của redirect loop, thay vì
tiếp tục phụ thuộc vào cookie parent-domain. Cookie có Domain được gửi tới
domain và mọi subdomain; OWASP cảnh báo cross-subdomain cookie làm rộng session
attack surface và session fixation risk. [1][2]

## 2. Baseline hiện tại

Flow hiện tại:

~~~text
Browser → erp.letron.vn → auth.letron.vn/login
        → auth.letron.vn/login/start → Lark
        → auth.letron.vn/api/auth/lark/callback
        → Set-Cookie: letron_sso; Domain=.letron.vn
        → erp.letron.vn → Portal Gateway → ERPNext /api/v1/*
~~~

Với leducanh@ledb.vn, runtime đã chứng minh:

- Lark authorization code + PKCE hoạt động.
- State và browser binding được dùng trong transaction.
- Callback production trả 303.
- Cookie parent-domain được gửi sang ERP.
- ERP mở được workspace và Gateway request trả 200.
- Redirect loop không tái hiện trong context sạch.

Nguyên nhân redirect loop trước remediation là lỗi session boundary:

~~~text
ERP thiếu session → Auth → Lark → callback thành công
→ ERP vẫn thiếu session → Auth → Lark → ...
~~~

Đây là lỗi giữa hai web origin, không phải lỗi PKCE hay bản thân Lark OAuth.

## 3. Kiến trúc đích

### 3.1 Ownership

| Thành phần | Ownership |
|---|---|
| Lark | Upstream authentication và group membership |
| Auth Server | Stable identity, Lark snapshot, user status, OIDC, policy |
| ERP BFF | ERP browser session, deep-link return và auth callback |
| Gateway | Authorization theo policy và assertion validation |
| ERPNext | Business data, native permission và business validation |
| Browser | Chỉ giữ ERP host-only session cookie |

Không tạo thêm password authority trong ERP. ERP User là projected identity để
Frappe thực thi permission, không phải nguồn login.

### 3.2 Session boundary

Auth dùng cookie host-only và ERP dùng cookie host-only khác:

~~~http
Set-Cookie: letron_sso=<opaque>; Secure; HttpOnly; SameSite=Lax; Path=/
Set-Cookie: __Host-letron_<app>_session=<opaque>; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Không cookie nào có Domain. Cookie Auth không gửi sang ERP và cookie ERP không
gửi sang Auth. ERP dùng namespace riêng cho `assets`, `purchase`, `accounts`;
prefix `__Host-` yêu cầu Secure, Path=/ và không có Domain; browser enforce các
thuộc tính này. [1][2]

### 3.3 Login flow mới

1. ERP kiểm tra ERP host-only cookie.
2. Nếu chưa có session, ERP tạo transaction trong PostgreSQL gồm state hash,
   nonce hash, code verifier hash, return path, expiry và consumed state.
3. ERP redirect tới OIDC authorization endpoint của Auth với exact redirect URI,
   state, nonce và PKCE S256.
4. Auth dùng Auth cookie nếu đã có; nếu chưa, redirect user tới Lark.
5. Auth callback hoàn tất Lark identity và group/policy refresh.
6. Auth redirect authorization code về ERP callback.
7. ERP callback kiểm tra state, nonce, issuer, audience và expiry, rồi đổi code
   server-to-server tại Auth token endpoint.
8. ERP tạo session opaque riêng, rotate session ID và phát hành ERP host-only
   cookie.
9. ERP redirect về return_path đã lưu trong transaction.

OAuth Security BCP yêu cầu exact redirect URI, transaction-specific PKCE và
chống open redirect; flow này bám theo các yêu cầu đó. [3]

### 3.4 Authorization flow mới

ERP BFF dùng ERP session để lấy user context server-side. Browser credential
không được forward sang Gateway.

Khuyến nghị Gateway nhận signed short-lived assertion do Auth cấp hoặc được ERP
BFF exchange từ Auth. Assertion cần có issuer, audience, stable subject,
tenant_key, union_id, subject_type, policy_version, issued_at, expiry, jti và
request_hash.

request_hash phải bao gồm method, canonical path, canonical query và SHA-256
body. Assertion sống tối đa 60 giây; Gateway kiểm tra identity và policy
server-side, không cấp quyền chỉ vì chữ ký hợp lệ.

Nếu tạm giữ HMAC, phải thêm body/query hash, audience, jti replay cache và
không forward browser Authorization header không cần thiết.

## 4. Redirect loop prevention

### 4.1 API không redirect vô hạn

ERP API/BFF route thiếu session phải trả JSON 401, không redirect HTML:

~~~json
{"error":"authentication_required","login_url":"/api/auth/login?return_to=..."}
~~~

Chỉ page navigation mới redirect. Fetch/XHR không được tạo redirect chain khó
quan sát.

### 4.2 Redirect budget

Mỗi login transaction có attempt_id và tối đa hai browser redirects. Khi
transaction expired, consumed hoặc callback lỗi, trả lỗi hữu hạn:

- AUTH_COOKIE_NOT_ACCEPTED
- OIDC_TRANSACTION_EXPIRED
- OIDC_CALLBACK_ORIGIN_MISMATCH
- ERP_SESSION_NOT_CREATED
- GATEWAY_SESSION_INVALID

Không redirect lại /login vô điều kiện khi callback hoặc session exchange fail.

### 4.3 Return URL

Chỉ lưu relative return_path trong transaction. Không redirect theo absolute URL
do browser gửi; nếu hỗ trợ absolute URL thì phải so exact origin với allowlist
rồi chuyển thành path.

## 5. Group sync và revoke cho leducanh@ledb.vn

Session exchange không tự giải quyết revoke. Trước khi Auth phát hành assertion:

1. Load external identity của leducanh@ledb.vn.
2. Nếu snapshot cũ hơn 60 giây, acquire distributed lease.
3. Một worker gọi Lark group membership.
4. Ghi snapshot và synced_at trong một transaction.
5. Nếu mất required access group, revoke Auth/ERP session và deny assertion.
6. Nếu Lark timeout, stale snapshot chỉ được dùng trong policy window; sau đó
   fail closed bằng authorization_unavailable.

Khi access bị remove, cần revoke Auth sessions, OIDC grants/artifacts và ERP
BFF sessions; disable ERP User, remove managed roles và ghi audit event. Restore
access phải yêu cầu snapshot mới và session renewal mới.

## 6. Policy và ERP role projection

Role ERP chỉ được sinh từ entitlement đã publish:

~~~text
Lark groups → published policy entitlements → policy roles → ERP Custom DocPerm
~~~

Không biến group Lark không có mapping thành role ERP tự động. Gateway phải
xác nhận role claim thuộc published policy version; ERP không chỉ kiểm tra prefix.

Policy publish phải tăng version đơn điệu, reject replay/downgrade, kiểm tra hash,
có trạng thái commit/readback và chỉ cho Gateway dùng version mới sau khi ERP
xác nhận publication.

## 7. Origin và browser contract

| Giá trị | Production |
|---|---|
| Auth public origin | https://auth.letron.vn |
| ERP public origin | https://erp.letron.vn |
| OIDC issuer | https://auth.letron.vn/api/oidc |
| ERP callback | https://erp.letron.vn/api/auth/oidc/callback |
| Lark callback | https://auth.letron.vn/api/auth/lark/callback |

OIDC client registration phải exact-match callback, không wildcard. Proxy chỉ
được forward canonical host/scheme; application không tin arbitrary Host hoặc
X-Forwarded-Host.

Browser phải dùng top-level Lark navigation, không phụ thuộc third-party iframe
cookie, không giữ credential trong localStorage/sessionStorage, bật HSTS và
dùng Secure, HttpOnly, SameSite=Lax, Path=/ cho session cookie.

## 8. Migration plan riêng cho leducanh@ledb.vn

### Phase 0 — Contract và observability

- Tạo ERP OIDC client với callback exact.
- Thêm correlation ID qua ERP → Auth → Lark callback → ERP.
- Đo redirect count, callback result, cookie/session exchange và Gateway errors.
- Không log code, token, cookie hoặc secret.

### Phase 1 — Shadow session

- (Lịch sử) Giữ flow parent-cookie trong giai đoạn shadow; flow production hiện
  tại đã chuyển sang host-only app session.
- Tạo ERP session exchange shadow cho leducanh@ledb.vn.
- So sánh identity, tenant, subject và policy; chưa đổi authorization.

### Phase 2 — Canary

- Bật BFF exchange chỉ cho leducanh@ledb.vn.
- Không gửi letron_sso sang ERP trong canary.
- Test clean browser, existing Auth session, refresh, deep link, back/forward,
  logout và login lại.
- Rollback bằng feature flag nếu callback/session exchange fail.

### Phase 3 — Gateway assertion

- Gateway hỗ trợ assertion mới và HMAC cũ trong thời gian chuyển tiếp.
- Bắt buộc body/query hash và replay protection.
- Readback identity/policy trước khi bật assertion mới.

### Phase 4 — Cutover

- Chuyển leducanh@ledb.vn sang ERP host-only session.
- Revoke letron_sso cũ.
- Xóa parent-domain cookie contract khỏi source/docs.
- Xóa fallback route cũ sau khi không còn traffic.
- Chỉ promote khi npm run check xanh.

## 9. Acceptance matrix

| Test | Expected |
|---|---|
| Clean browser → ERP | Một login flow, không loop |
| Existing Auth session → ERP | Không cần Lark login lại |
| Lark callback | ERP host-only cookie được tạo |
| ERP refresh | Không redirect lại khi session còn hạn |
| Deep link path/query | Quay đúng path/query |
| Cancel tại Lark | Lỗi hữu hạn, không loop |
| Reload callback | Transaction đã consume |
| Xóa Auth cookie | Một redirect tới login |
| Logout | ERP/Auth session bị revoke |
| Login lại | Session mới |
| Revoke Lark group | Gateway deny và session revoke trong SLA |
| Lark timeout | Stale window hữu hạn rồi fail closed |
| Gateway replay | Request thứ hai bị reject |
| Body/query tamper | Assertion bị reject |
| Lark CORS phụ | Không block nếu callback hoàn tất |
| Contract mismatch | Health/startup báo lỗi rõ |

## 10. Rollback

Rollback là chuyển feature flag và revoke session mới, không sửa database thủ
công:

1. Tắt ERP_BFF_SESSION_EXCHANGE_ENABLED.
2. Cho phép flow cũ trong rollback window giới hạn.
3. Giữ Auth/ERP deployment cùng commit.
4. Revoke ERP sessions của release lỗi.
5. Kiểm tra lại leducanh@ledb.vn bằng clean browser.
6. Lưu request IDs và callback/session state, không lưu credential.

## 11. Đánh giá lựa chọn

| Phương án | Redirect resilience | Security boundary | Quyết định |
|---|---:|---:|---|
| Giữ cookie parent-domain | Trung bình | Yếu hơn | Chỉ workaround |
| Reverse proxy cùng origin | Cao | Tốt | Có thể dùng |
| ERP BFF session exchange | Cao | Tốt nhất | Khuyến nghị |
| ERP tự giữ Lark token | Thấp | Rất rủi ro | Loại bỏ |

## 12. Kết luận

BFF session exchange với hai host-only cookies, OIDC Authorization Code + PKCE,
exact callback allowlist, bounded redirect state machine và signed short-lived
Gateway assertion là phương án đích.

Nó loại bỏ nguyên nhân gốc của redirect loop và giảm rủi ro subdomain cookie,
trong khi giữ ownership: Lark là upstream identity, Global Portal sở hữu policy,
ERPNext thực thi business permission.

Acceptance browser của `leducanh@ledb.vn` và CLI business real-test là hai bằng
chứng riêng. Browser chứng minh Lark OAuth/handoff; CLI chứng minh app session,
Gateway routing và business flow. Không dùng một loại acceptance để thay thế
loại còn lại.

## 13. Trạng thái triển khai ngày 2026-09-11

Đã triển khai phần mã nguồn của phương án BFF exchange:

- Auth cookie đã trở thành host-only; ERP nhận app-scoped cookie
  (`__Host-letron_assets_session`, `__Host-letron_purchase_session` hoặc
  `__Host-letron_accounts_session`) và không còn phụ thuộc cookie cha
  `.letron.vn`.
- Lark callback có one-time ERP handoff TTL 2 phút; ERP đổi handoff lấy session
  server-side trong Redis và không đưa gateway token vào URL sau callback.
- ERP API route chuyển gateway session qua header server-to-server; không gửi
  ERP cookie thô sang Auth Gateway.
- Auth Gateway refresh group Lark theo request khi snapshot stale, gắn chữ ký
  với method/path/query/body và chống replay request-id.
- Logout thu hồi ERP gateway session và Auth SSO session tương ứng.
- Deep-link/return path được giới hạn same-origin, không cho `/api/` và redirect
  dùng status 303.

Đã kiểm tra tĩnh/local: Prisma validate, Auth typecheck, ERP typecheck, Auth
tests (20/20), Auth build, ERP lint, Python compileall và `git diff --check` đều
xanh; Auth lint chỉ còn các warning unused có sẵn. Chưa chạy migration hoặc
browser/production acceptance. Trước khi promote phải chạy migration
`202609110001_erp_bff_session`, reload/restart đúng launcher, kiểm tra secret
Redis/Auth, rồi chạy clean-browser flow riêng cho `leducanh@ledb.vn` theo bảng
acceptance ở trên.

## Sources

[1] OWASP Foundation, Session Management Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

[2] MDN Web Docs, Set-Cookie header:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie

[3] IETF RFC 9700, OAuth 2.0 Security Best Current Practice:
https://www.rfc-editor.org/rfc/rfc9700.html

[4] IETF RFC 10017, OAuth 2.0 for Browser-Based Applications:
https://www.rfc-editor.org/rfc/rfc10017.html
