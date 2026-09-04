const messages: Record<string, string> = {
  lark_callback_rejected: "Lark đã từ chối hoặc không trả về đủ dữ liệu xác thực.",
  lark_tenant_not_allowed: "Tài khoản này không thuộc Lark tenant được phép.",
  lark_email_missing: "Tài khoản Lark chưa có email doanh nghiệp để liên kết.",
  lark_subject_missing: "Lark không trả về định danh người dùng ổn định.",
  login_start_failed: "Không thể bắt đầu phiên đăng nhập.",
  interaction_failed: "Phiên SSO không còn hợp lệ hoặc đã hết hạn.",
  login_failed: "Đăng nhập không thành công.",
};

export default async function ErrorPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string }>;
}) {
  const { code = "login_failed" } = await searchParams;
  return (
    <main>
      <section className="card">
        <div className="eyebrow">Letron SSO</div>
        <h1>Không thể đăng nhập</h1>
        <p>{messages[code] ?? messages.login_failed}</p>
        <div className="actions">
          <Link className="button" href="/login">Thử lại</Link>
          <Link className="button secondary" href="/">Về trang chính</Link>
        </div>
      </section>
    </main>
  );
}
import Link from "next/link";
