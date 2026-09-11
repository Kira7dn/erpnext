# Letron ERP Next.js frontend

Fresh Next.js App Router scaffold created with the latest available
`create-next-app` CLI in this environment.

Included:

- TypeScript
- Tailwind CSS v4
- ESLint
- App Router and `src/` directory
- shadcn/ui CLI v4 with the Radix base
- Geist and Geist Mono font setup
- TanStack Query with shared client request/error handling
- Separate lightweight PWA manifests for Accounting and Assets

PWA routes:

- `/accounts/manifest.webmanifest` — LeTRON-Kế toán
- `/assets/manifest.webmanifest` — LeTRON-Tài sản

The PWA layer intentionally has no service worker and does not cache API
responses. SSO is provided by Lark, while all business data remains online through the Letron Gateway
Gateway.

Run from this directory:

```powershell
npm run dev
npm run typecheck
npm run lint
npm run build
```
