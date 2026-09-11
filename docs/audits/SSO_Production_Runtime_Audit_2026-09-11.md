# Letron SSO production runtime audit — 2026-09-11

## Phạm vi

Audit bằng Playwright trên `https://erp.letron.vn/` với browser context riêng, sau đó đối chiếu request chain, cookie metadata và Vercel logs của Auth/ERP. Không ghi secret hoặc giá trị cookie vào báo cáo.

## Kết luận

Production SSO đã chạy thành công với `leducanh@ledb.vn` trong flow browser đã
kiểm chứng. Cookie `letron_sso` được phát hành ở domain `.letron.vn`, ERP nhận
được cookie từ Auth, callback quay lại đúng URL và trang ERP mở được.

Kết luận này chỉ khẳng định login/redirect happy path và không đồng nghĩa rằng
mọi failure mode production đã được loại bỏ. Các rủi ro còn lại cần tập trung
theo dõi là redirect/cookie, browser security blocking, upstream Lark request
phụ và session lifecycle.

## Flow runtime đã kiểm chứng

### Trước đăng nhập

| Bước | Request | Kết quả |
|---|---|---:|
| 1 | `GET https://erp.letron.vn/` | `307` |
| 2 | `GET https://auth.letron.vn/login?return_to=https%3A%2F%2Ferp.letron.vn%2F` | `307` |
| 3 | `GET https://auth.letron.vn/login/start?return_to=...` | `303` |
| 4 | `GET https://open.larksuite.com/open-apis/authen/v1/authorize` | `302` |
| 5 | `GET https://accounts.larksuite.com/...` | `200` trang đăng nhập Lark |

Authorization URL có đúng `client_id`, PKCE `code_challenge`, `state`, scope `contact:user.email:readonly` và callback `https://auth.letron.vn/api/auth/lark/callback`.

### Sau đăng nhập

| Bước | Request | Kết quả |
|---|---|---:|
| 1 | `GET https://auth.letron.vn/api/auth/lark/callback?code=...&state=...` | `303` |
| 2 | `GET https://erp.letron.vn/` | `307` |
| 3 | `GET https://erp.letron.vn/accounts` | `200` |

`/` → `/accounts` là redirect nội bộ của landing page ERP, không phải redirect loop và không phải callback sai.

## Cookie và identity evidence

- Cookie session: `letron_sso`.
- Domain: `.letron.vn`.
- Browser context sau callback gửi được session sang `erp.letron.vn`.
- UI ERP hiển thị user `leducanh@ledb.vn` và trạng thái “Đã đăng nhập”.
- Các route `/accounts/*` và request Gateway sau đăng nhập trả `200`.

## Các hiện tượng và nguyên nhân

### SSO-001 — High — Redirect loop trước remediation (đã xử lý)

- Hiện tượng: Chrome báo `ERR_TOO_MANY_REDIRECTS` tại `erp.letron.vn`.
- Nguyên nhân: cookie cũ chỉ thuộc host `auth.letron.vn`; ERP không nhận được session nên liên tục đẩy người dùng về Auth/Lark.
- Xử lý: session cookie được phát hành với parent domain `.letron.vn`.
- Evidence hiện tại: Playwright login thành công và ERP nhận `letron_sso`.

### SSO-002 — High — Browser-facing auth entrypoint (đã xử lý)

- Hiện tượng: browser bị đưa trực tiếp tới API endpoint trong lúc bắt đầu login.
- Xử lý: flow browser dùng `/login/start`; endpoint này tạo transaction/cookie rồi chuyển tiếp tới cùng Lark OAuth contract.
- Callback vẫn giữ nguyên `/api/auth/lark/callback` theo cấu hình Lark.

### SSO-003 — High — Build production phụ thuộc file `.env` local (đã xử lý)

- Hiện tượng: Vercel build lỗi `ENOENT` khi mở `/vercel/path0/.env`.
- Nguyên nhân: wrapper build giả định file `.env` luôn tồn tại trong checkout.
- Xử lý: wrapper bỏ qua riêng lỗi `ENOENT`; biến production vẫn do Vercel Environment Variables cung cấp.
- Evidence hiện tại: Auth và ERP deployment mới đều `READY`.

### SSO-004 — Medium — Browser console có CORS errors từ Lark (không chặn flow đã test)

- Hiện tượng: browser console ghi lỗi CORS với:
  - `internal-api-security-sg.feishu.cn/web/r/token`
  - `internal-api-security-sg.feishu.cn/web/common`
- Phạm vi: request nội bộ của trang Lark từ origin `accounts.larksuite.com`.
- Kết quả runtime: trang Lark vẫn tải, đăng nhập hoàn tất, callback trả `303`, session và ERP hoạt động.
- Kết luận: đây là lỗi phụ của Lark/browser integration trong run hiện tại,
  chưa có bằng chứng là blocker của Letron. Tuy nhiên không được coi là vô hại
  tuyệt đối: nếu Lark thay đổi login flow và một request trong nhóm này trở
  thành request bắt buộc, browser có thể dừng trước khi phát hành authorization
  code.

### SSO-005 — Medium — Lark tracking/captcha/analytics request bị lỗi hoặc abort

- Hiện tượng: một số request tracking, captcha hoặc analytics trả `FAILED`/`ERR_ABORTED`.
- Kết quả trong run này: không ảnh hưởng callback, cookie hoặc trang ERP.
- Rủi ro production: captcha/tracking có thể thay đổi vai trò theo từng tenant,
  browser hoặc lần đăng nhập; cần phân biệt request bắt buộc với telemetry phụ.
- Hành động: không sửa Letron chỉ vì request phụ lỗi, nhưng phải monitor nếu
  callback `code/state` không xuất hiện hoặc trang Lark không hoàn tất.

### SSO-006 — Medium — Context sạch không có sẵn phiên Lark

- Hiện tượng: mỗi Playwright context mới bị đưa tới trang đăng nhập Lark.
- Nguyên nhân: context được tạo mới, không dùng cookie Chrome hiện tại.
- Kết luận: hành vi đúng, không phải lỗi Auth. Sau khi đăng nhập trong cùng context, flow hoàn tất.

### SSO-007 — Low — `/` không phải trang workspace cuối

- Hiện tượng: callback quay về `/`, sau đó browser tới `/accounts`.
- Nguyên nhân: ERP landing route tự chọn workspace kế toán mặc định.
- Kết luận: redirect ban đầu đúng; `/accounts` là điều hướng UI tiếp theo.

## Deployment evidence

- ERP production: deployment trạng thái `READY`, branch `main`, commit `c70adb7896d61f2010451cf019bbeda271642d32`.
- Auth production: deployment trạng thái `READY`, branch `main`, commit `c70adb7896d61f2010451cf019bbeda271642d32`.
- Auth production có các route `/login/start`, `/api/auth/lark/callback` và `/api/auth/session/refresh`.
- Vercel logs ghi nhận callback Auth `303`, ERP `/accounts` `200`, và các request Gateway `200`.

## Rủi ro còn lại và giới hạn bằng chứng

- Chưa kiểm thử redirect về một URL ERP có path/query khác `/`; code contract đã giới hạn absolute URL về đúng origin `https://erp.letron.vn` và giữ nguyên path/query.
- Chưa kiểm thử logout rồi login lại trong cùng browser context.
- CORS của Lark vẫn xuất hiện trong console và nên được theo dõi nếu Lark thay đổi login flow.
- Chưa coi các request Lark tracking là lỗi nghiệp vụ vì callback và ERP acceptance đã pass.

## Trạng thái cuối

| Hạng mục | Trạng thái |
|---|---|
| ERP → Auth redirect | Pass |
| Auth → Lark OAuth | Pass |
| Lark → Auth callback | Pass |
| Session cookie parent domain | Pass |
| Auth → ERP return | Pass |
| ERP workspace load | Pass |
| Redirect loop | Không tái hiện |
| Lark phụ CORS/analytics | Còn thấy, không blocking |

## Production risk review — tập trung redirect và browser

### R-01 — High — Cookie không được gửi sang ERP

Đây là nguyên nhân đã gây `ERR_TOO_MANY_REDIRECTS` trước remediation. Nếu cookie
quay lại host-only `auth.letron.vn`, bị set với domain/path sai, bị browser loại
bỏ vì `Secure`/scheme, hoặc bị proxy rewrite, ERP sẽ không thấy session và tạo
vòng lặp:

```text
ERP thiếu session → Auth login → Lark → callback → ERP thiếu session → lặp lại
```

Mitigation hiện tại là parent-domain cookie `.letron.vn`; run với
`leducanh@ledb.vn` đã chứng minh cookie được gửi sang ERP.

Điều cần monitor sau deploy:

- callback có `Set-Cookie` không;
- cookie có đúng domain `.letron.vn`, path `/`, Secure và HttpOnly không;
- request tiếp theo tới `erp.letron.vn` có cookie không;
- số lượng redirect 307/303 liên tiếp trên cùng request chain.

### R-02 — High — Origin/callback URL mismatch

Nếu Auth start dùng một origin nhưng callback dựng origin khác do proxy header,
Lark sẽ từ chối `redirect_uri` hoặc callback transaction sẽ không khớp. Đây là
failure mode gây đứng ở Lark, `20029`, callback rejected hoặc quay lại login.

Flow hiện tại đã dùng canonical origin ở start/callback. Acceptance đã xác nhận
callback production đúng `https://auth.letron.vn/api/auth/lark/callback`.

Chưa kiểm thử return URL ERP có path/query khác `/`; đây là rủi ro còn lại nếu
browser được mở từ deep link.

### R-03 — High — Browser chặn hoặc cảnh báo URL Auth/Lark

Entry route phải là `/login/start`. Việc điều hướng trực tiếp tới route API
`/api/auth/lark/start` từng gây cảnh báo Dangerous Site trong Chrome.

Nếu frontend, bookmark, Lark app hoặc redirect config vẫn trỏ route cũ, user có
thể thấy cảnh báo browser trước khi tới Lark. Runtime hiện tại đã dùng route mới
và không tái hiện cảnh báo trong flow chuẩn.

### R-04 — Medium — SameSite/cross-subdomain behavior

Auth và ERP dùng hai subdomain khác nhau. Thay đổi cookie flags, domain hoặc
scheme có thể khiến browser không gửi session dù callback vẫn trả `303`.
`SameSite=Lax` phù hợp với redirect GET đã test, nhưng không nên đổi sang flow
POST callback nếu chưa test lại browser.

### R-05 — Medium — Lark upstream UI/CORS thay đổi

Các request tới `feishu.cn` hiện có CORS/abort nhưng không chặn
`leducanh@ledb.vn`. Đây là dependency ngoài Letron; không nên xem HTTP 200 của
trang Lark là đủ. Acceptance cần kiểm tra authorization code được trả về và
callback thực sự hoàn tất.

### R-06 — Medium — Auth/ERP deployment không cùng contract

Auth và ERP phải cùng các giá trị contract tương ứng:

- `LETRON_AUTH_BASE_URL`;
- `LETRON_ERP_APP_BASE_URL`;
- `FRAPPE_ERP_NEXT_URL`;
- `LETRON_INTERNAL_API_SECRET`;
- cookie/JWKS configuration;
- allowed Lark tenant và callback URL.

Deployment cùng commit đã giảm nguy cơ source drift, nhưng Vercel environment
variables vẫn là state độc lập. Sai một biến có thể biểu hiện như redirect loop,
401 Gateway hoặc callback rejected dù deployment đều `READY`.

## Browser failure runbook

Khi `leducanh@ledb.vn` bị lỗi production, thu thập theo đúng thứ tự sau:

1. Xóa riêng site data của `auth.letron.vn` và `erp.letron.vn`, mở context mới.
2. Xác nhận `/` → `/login` → `/login/start` → Lark.
3. Kiểm tra không có redirect tới `/api/auth/lark/start` cũ.
4. Kiểm tra authorization request có `state`, PKCE và callback production.
5. Kiểm tra callback trả `303`, không phải `400`, `401` hoặc `5xx`.
6. Kiểm tra cookie `letron_sso` xuất hiện ở `.letron.vn` và được gửi ở request
   ERP kế tiếp.
7. Nếu callback pass nhưng ERP trả `401/403`, kiểm tra Gateway identity/policy;
   không tiếp tục xóa cookie và retry vô hạn.
8. Nếu chỉ có CORS/abort ở request phụ Lark nhưng callback pass, phân loại là
   non-blocking và lưu lại thời điểm/browser/version để theo dõi.

## Handover decision

### Được chấp nhận

- `leducanh@ledb.vn` đăng nhập production qua Lark.
- Callback production và session parent-domain hoạt động.
- ERP mở được workspace và Gateway request thành công.
- Không tái hiện redirect loop trong browser context sạch.

### Điều kiện cần theo dõi sau bàn giao

- Deep-link return URL có path/query.
- Logout rồi login lại trong cùng browser context.
- Cookie flags/domain sau mỗi deployment.
- Tần suất 307/303 bất thường.
- Callback lỗi tăng theo browser hoặc thay đổi từ Lark.
- Gateway 401/403 sau khi callback đã pass.

### Giới hạn kết luận

Báo cáo này không claim đã chứng minh revoke Lark group, stale-lock hoặc full
authorization lifecycle. Đây là các gate riêng; chúng không cần thiết để kết
luận flow redirect/login của `leducanh@ledb.vn` đã pass, nhưng cũng không được
ẩn dưới nhãn “mọi rủi ro SSO đã đóng”.
