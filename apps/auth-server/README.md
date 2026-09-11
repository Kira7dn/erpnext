# Letron Auth Server

Next.js SSO server chạy trên Vercel Functions. Lark là upstream identity provider; các ứng dụng Letron dùng máy chủ này như một OpenID Connect Provider.

## Phạm vi hiện tại

- Lark OAuth authorization-code với `state` và PKCE S256.
- Chỉ cho phép một Lark tenant qua `LARK_ALLOWED_TENANT_KEY`.
- Phiên SSO OIDC opaque 8 giờ, token chỉ được lưu dưới dạng SHA-256 trong
  PostgreSQL. ERP handoff dùng Gateway session riêng với TTL mặc định 24 giờ.
- OIDC Authorization Code Flow, `openid profile email groups`, bắt buộc PKCE.
- OIDC clients được đăng ký tĩnh trong bảng `oidc_client`; không có dynamic registration, implicit, password, refresh-token hoặc device flow.
- Không lưu Lark access token sau khi lấy thông tin người dùng.
- Adapter ERPNext bắt buộc PKCE, kiểm tra state, browser binding, nonce, chữ ký ID token, issuer, audience và UserInfo subject.
- Lark User Group là nguồn gán quyền và vòng đời truy cập. Danh tính ổn định là `tenant_key + union_id`, không phải email.
- Auth Server phát snapshot `group_id`; ERPNext ánh xạ và chỉ thay đổi các role nằm trong allowlist quản lý bởi Lark.
- Global Portal là control plane cho centrally managed access policy; policy được
  publish thành projection xuống ERPNext.
- RBAC của Portal chỉ có dạng `Lark User Group → OpenAPI resource → CRUD
  operation`; không có multi-tenant authorization, field-level permission,
  record/data scope hoặc metadata-driven form generator.
- ERPNext vẫn là enforcement engine cho Role Permission, Workflow và User
  Permission trên mọi request; Portal không thay thế authorization runtime.
- Global Portal suy ra role từ cùng mapping và chỉ hiển thị ứng dụng/phân hệ phù
  hợp. Đây là presentation filter; ERPNext vẫn phải kiểm tra authorization cho
  mọi request.
- Trang chủ là LeTRON-Global Portal; portal chỉ phụ trách xác thực, cấu hình và quản trị access policy. Các ứng dụng nghiệp vụ mở độc lập và dùng chung session SSO.

## Chạy local

1. Tạo PostgreSQL serverless trên Neon hoặc Vercel Marketplace và lấy pooled `DATABASE_URL`.
2. Copy `.env.example` thành `.env.local`. Có thể giữ `LARK_APP_ID` và `LARK_APP_SECRET` trong file `.env` ở root repo khi chạy local; production phải khai báo trong Vercel Environment Variables.
3. Chạy `npm run keys:generate` rồi đưa ba giá trị sinh ra vào `.env.local`/Vercel.
4. Trong Lark Developer Console, đăng ký callback chính xác `http://localhost:3000/api/auth/lark/callback` cho local và `${LETRON_AUTH_BASE_URL}/api/auth/lark/callback` cho production.
5. Bật các quyền ứng dụng cần thiết để API `authen/v1/user_info` trả về email hoặc enterprise email; auth server cố ý từ chối tài khoản không có email.
6. Để bật đồng bộ role, cấp application permission `contact:group:readonly`, đặt Contacts data scope bao phủ người dùng ERP, tạo các User Group và cấu hình mapping bằng `group_id`.
7. Chạy migration rồi khởi động:

```powershell
npm run db:migrate
npm run dev
```

Không cần ERPNext hoặc Docker để chạy auth server này.

## Global Portal client

ERPNext không còn là OIDC client và không có callback/login native. Ứng dụng ERP
được mở qua Global Portal; Portal giữ session `letron_sso`, kiểm tra policy và
chuyển request nghiệp vụ qua Gateway với claims đã ký.

URL đặt làm trang chủ Web App trong Lark để đăng nhập vào ứng dụng nghiệp vụ là:

```text
http://localhost:3000/login?return_to=http%3A%2F%2Flocalhost%3A3001%2Faccounts
```

LeTRON-Global Portal tự động chuyển qua Lark khi chưa có phiên, sau đó trả người dùng về
ứng dụng đã yêu cầu đăng nhập. LeTRON-Global Portal không còn hiển thị thẻ hoặc launch
URL của ERP.

`localhost` chỉ hợp lệ với Lark Desktop chạy trên cùng máy. Lark mobile và máy
khác không truy cập được server local; môi trường dùng chung phải có HTTPS
public origin và đăng ký chính xác callback theo origin đó.

## Đồng bộ role từ Lark

Giữ `LARK_GROUP_SYNC_ENABLED=false` và `LETRON_SSO_ROLE_SYNC_ENABLED=false` cho tới khi quyền Lark và các `group_id` thật đã sẵn sàng. Sau đó cấu hình hai phía theo `.env.example` và bật cả hai cờ.

Một người dùng có thể thuộc nhiều Lark Contact User Group. `ERP - Access` là
group cổng bắt buộc; Portal render đúng các group đang tồn tại và cấp OpenAPI
CRUD permission trực tiếp cho từng group. Không tạo group theo từng cá nhân và
không sao chép role native của ERPNext sang Lark.

Thiết kế group, quy tắc membership, bảng mapping khởi đầu và checklist triển
khai nằm tại
[Lark SSO Role Design and Next Steps](../../docs/notes/Lark_SSO_Role_Design_and_Next_Steps_2026-09-05.md).

Portal dùng policy CRUD đã publish làm nguồn quyền duy nhất. Không còn mapping
group-to-native-role trong environment; mỗi entitlement được định danh duy nhất
từ Lark group và projection ERP dùng role kỹ thuật `Letron Policy - group-*`.

## Global Access Policy và OpenAPI gateway

Trang `/admin/access-policy` dành riêng cho Global Access Admin Lark group được
quản lý cố định trong runtime config. Policy được lưu trong PostgreSQL theo version và
autosave thành bản published mới; không có draft/approve/rollback workflow.
Policy v1 chỉ tham chiếu các public OpenAPI routes đã đăng ký.

`/api/gateway/*` là gateway server-side: phải có Global Portal session, published
policy và entitlement từ Lark group phù hợp. Route ngoài public registry hoặc
operation không được cấp sẽ fail closed. Gateway truyền authorization context
bằng header HMAC nội bộ; ERP origin phải private và chỉ nhận traffic từ gateway.
Không đưa authorization decision vào query string hoặc tin header do client gửi.

Gateway và policy publication dùng lại `FRAPPE_ERP_NEXT_URL` và
`LETRON_INTERNAL_API_SECRET` hiện có. Đây là app nội bộ nên không tạo thêm ERP
credential riêng trong Auth Server; ERP origin vẫn phải nằm trong mạng nội bộ.
nếu chưa có ERP-side verifier, policy projection readback và direct-origin deny
acceptance.

Gateway làm mới group membership khi snapshot quá hạn, có lease chống gọi trùng.
Session lookup không gọi network Lark. User không hoạt động không tạo API call
Lark và role sync không dùng cron. Endpoint
nội bộ dùng bearer secret riêng; không dùng Lark App Secret và không được công
khai cho client.

Luồng vòng đời:

- Lần đăng nhập đầu: nếu danh tính thuộc group truy cập bắt buộc, ERP tạo `System User` theo JIT và lưu liên kết `tenant_key + union_id`.
- Email hoặc tên đổi trong Lark: ERP cập nhật User đã liên kết theo stable identity, không dò ghép lại bằng email.
- Bị gỡ khỏi group truy cập hoặc Auth User bị disable: ERP gỡ role do Lark quản lý, disable User và xóa session.
- Được thêm lại: ERP enable User và khôi phục role theo mapping; local admin block vẫn được tôn trọng.
- Endpoint lỗi: login mới từ chối snapshot quá `LETRON_SSO_SNAPSHOT_MAX_AGE_SECONDS`; request đang hoạt động được dùng snapshot gần nhất trong cửa sổ cho phép. Khi lần đồng bộ thành công gần nhất quá `LETRON_SSO_STALE_LOCK_SECONDS`, User bị disable và session hiện có bị xóa. Snapshot mới hợp lệ sẽ mở khóa.

Thay đổi trực tiếp các role/permission thuộc centrally managed policy trong
ERPNext bị chặn hoặc phải tạo drift alert. Role ngoài allowlist và policy chưa
được Global Portal quản lý vẫn do ERP/operator quản lý. ERPNext luôn là nơi
enforce permission runtime.

Break-glass chỉ chạy bằng lệnh operator không public, có lý do và TTL bị giới hạn bởi `LETRON_SSO_BREAK_GLASS_MAX_SECONDS`:

```powershell
docker exec `
  -e LETRON_BREAK_GLASS_USER=user@example.com `
  -e LETRON_BREAK_GLASS_ROLE_NAMES="Desk User,Accounts User" `
  -e LETRON_BREAK_GLASS_REASON="Incident reference" `
  -e LETRON_BREAK_GLASS_TTL_SECONDS=900 `
  erpnext-backend-1 bench --site frontend execute letron_api.auth.sso_admin.break_glass_from_environment
```

Không dùng break-glass để vượt qua việc bị gỡ khỏi group truy cập hoặc local admin block. Mọi lần JIT, thu hồi, reconcile, stale-lock và break-glass được ghi vào `Letron SSO Audit Log`.

Frappe scheduler vẫn phục vụ các job ERP khác nhưng không tham gia đồng bộ role
Lark. Không thêm lại cron quét toàn bộ identity; Gateway kiểm tra policy trên
mỗi request và chỉ đồng bộ snapshot khi cần.

ERP chỉ được projection các role kỹ thuật có prefix `Letron Policy - group-`;
`Administrator`, `All`, `Guest` và `System Manager` không bao giờ được quản lý bởi Portal.

Issuer: `${LETRON_AUTH_BASE_URL}/api/oidc`

Discovery: `${LETRON_AUTH_BASE_URL}/api/oidc/.well-known/openid-configuration`

## Kiểm chứng

Gate Auth Server:

```powershell
npm run check
npm run db:migrate
```

`npm run check` gồm Prisma validation, TypeScript, ESLint, unit test và
production build. Sau khi cả Auth Server và ERP chạy, kiểm tra:

```text
GET http://localhost:3000/api/health
GET http://localhost:8080/api/method/letron_api.control.api.health
```

Health Auth phải báo group sync enabled. Health ERP phải báo
`sso_role_sync.enabled=true`, `installed=true` và identity ở trạng thái
`Active`. Bằng chứng on-demand yêu cầu `last_sync_at` tự tăng sau khi chờ hết
`LETRON_SSO_REQUEST_CHECK_INTERVAL_SECONDS` rồi gửi một request ERP đã xác thực;
không dùng reconcile thủ công. Gate cuối cùng vẫn là mở Web App thật trong Lark
Desktop, chọn ERP và vào được `/desk`.

### Sau khi thay đổi Prisma schema

Mỗi lần sửa `prisma/schema.prisma`, phải chạy đủ các bước sau:

```powershell
npm run db:generate
npm run db:migrate
npm run check
npm run dev
```

Dev server phải được restart sau `db:generate`. Nếu không, Next.js có thể vẫn
giữ Prisma Client cũ trong memory và phát sinh lỗi `column does not exist` dù
database migration đã thành công.

## Vercel

Đặt Root Directory thành `apps/auth-server`, khai báo toàn bộ biến trong `.env.example`, sau đó chạy migration từ CI hoặc máy quản trị trước khi promote deployment. Runtime không giữ session hoặc OAuth state trong memory; tất cả state bền vững nằm trong PostgreSQL.
