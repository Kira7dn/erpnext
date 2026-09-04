<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Letron Auth Server rules

- Đây là Global Portal và OIDC Provider dùng Lark làm upstream; giữ các endpoint
  auth hiện tại trong server-side API Routes và tương thích Vercel Functions.
- Runtime không được phụ thuộc state trong memory. OAuth transaction, session,
  OIDC artifact, client và external identity phải nằm trong PostgreSQL.
- Stable Lark identity là `tenant_key + union_id`. Không fallback `open_id`,
  không ghép identity mới với Auth User cũ theo email và phải fail closed khi
  email thuộc identity khác.
- Không lưu Lark user access token sau callback. Tenant access token chỉ được
  cache ngắn hạn để gọi API group membership.
- Endpoint snapshot nội bộ phải yêu cầu bearer secret riêng, trả version rõ
  ràng và giữ lỗi theo từng identity để một user lỗi không chặn cả batch.
- Không đưa secret hoặc giá trị thật từ `.env` vào source, test, README hay log.
- Thay đổi Prisma schema phải có migration; production chạy
  `npm run db:migrate` trước khi promote deployment.
- Gate local: `npm run check`. Kiểm tra Auth Server riêng không yêu cầu
  ERPNext/Docker; chỉ chạy ERP khi cần acceptance OIDC end-to-end.
