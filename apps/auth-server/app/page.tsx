import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getEnv } from "../src/server/env";
import {
  hasErpAccess,
  parseLarkRoleMapping,
  rolesForLarkGroups,
  visibleErpFeatures,
} from "../src/server/portal-access";
import { getUserBySessionToken, SESSION_COOKIE } from "../src/server/session";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const cookieStore = await cookies();
  const user = await getUserBySessionToken(cookieStore.get(SESSION_COOKIE)?.value);
  if (!user) redirect("/api/auth/lark/start?return_to=/");

  const env = getEnv();
  const roles = rolesForLarkGroups(user.groupIds, parseLarkRoleMapping(env.LETRON_SSO_LARK_ROLE_MAPPING));
  const canAccessErp = hasErpAccess(roles);
  const erpFeatures = visibleErpFeatures(roles);
  const erpBaseUrl = env.LETRON_SSO_ERP_BASE_URL ?? "http://localhost:8080";
  const erpUrl = `${erpBaseUrl}/api/method/letron_api.sso.launch`;
  const initials = user.displayName
    .split(/\s+/)
    .filter(Boolean)
    .slice(-2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <main className="portal-shell">
      <div className="portal-glow portal-glow-one" />
      <div className="portal-glow portal-glow-two" />
      <div className="portal-container">
        <header className="portal-header">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">L</span>
            <span>
              <strong>LETRON</strong>
              <small>GLOBAL PORTAL</small>
            </span>
          </div>
          <div className="user-chip" title={user.email}>
            <span className="user-avatar" aria-hidden="true">{initials || "L"}</span>
            <span className="user-copy">
              <strong>{user.displayName}</strong>
              <small>{user.email}</small>
            </span>
          </div>
        </header>

        <section className="portal-hero">
          <div className="eyebrow">Không gian làm việc Letron</div>
          <h1>Chào mừng trở lại, {user.displayName}</h1>
          <p>Truy cập các hệ thống nội bộ bằng một phiên đăng nhập Lark duy nhất.</p>
        </section>

        <section className="applications" aria-labelledby="applications-title">
          <div className="section-heading">
            <div>
              <h2 id="applications-title">Ứng dụng</h2>
              <p>Các công cụ được cấp cho tài khoản của bạn.</p>
            </div>
            <span className="app-count">{canAccessErp ? 1 : 0} ứng dụng</span>
          </div>

          <div className="app-grid">
            {canAccessErp ? (
              <a className="app-card" href={erpUrl}>
                <div className="app-card-topline">
                  <span className="app-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" role="img">
                      <path d="M4 5.5 12 2l8 3.5v6.8c0 4.4-3.2 8.2-8 9.7-4.8-1.5-8-5.3-8-9.7V5.5Z" />
                      <path d="M8.2 8.2h7.6M8.2 12h7.6M8.2 15.8h4.5" />
                    </svg>
                  </span>
                  <span className="status-pill"><i /> Sẵn sàng</span>
                </div>
                <div className="app-card-body">
                  <h3>Letron ERP</h3>
                  <p>Những phân hệ hiển thị dưới đây được xác định từ Lark User Group của bạn.</p>
                  <ul className="feature-list" aria-label="Các tính năng ERP được cấp">
                    {erpFeatures.map((feature) => <li key={feature.id}>{feature.label}</li>)}
                  </ul>
                </div>
                <div className="app-card-footer">
                  <span>SSO qua Lark</span>
                  <span className="launch-arrow" aria-hidden="true">→</span>
                </div>
              </a>
            ) : (
              <div className="empty-app-state" role="status">
                <span className="empty-app-icon" aria-hidden="true">○</span>
                <h3>Chưa có ứng dụng được cấp</h3>
                <p>Tài khoản của bạn chưa thuộc User Group có quyền sử dụng ứng dụng Letron.</p>
              </div>
            )}
          </div>
        </section>

        <footer className="portal-footer">
          <span>Letron Group · Internal systems</span>
          <form action="/api/auth/logout" method="post">
            <button className="text-button" type="submit">Đăng xuất</button>
          </form>
        </footer>
      </div>
    </main>
  );
}
