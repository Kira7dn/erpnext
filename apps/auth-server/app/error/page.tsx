import Link from "next/link";

const messages: Record<string, string> = {
  lark_callback_rejected: "Lark đã từ chối hoặc không trả về đủ dữ liệu xác thực.",
  lark_tenant_not_allowed: "Tài khoản này không thuộc Lark tenant được phép.",
  lark_email_missing: "Tài khoản Lark chưa có email doanh nghiệp để liên kết.",
  lark_subject_missing: "Lark không trả về định danh người dùng ổn định.",
  login_start_failed: "Không thể bắt đầu phiên đăng nhập.",
  interaction_failed: "Phiên SSO không còn hợp lệ hoặc đã hết hạn.",
  login_failed: "Đăng nhập không thành công.",
};

export default async function ErrorPage({ searchParams }: { searchParams: Promise<{ code?: string }> }) {
  const { code = "login_failed" } = await searchParams;
  return <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4"><section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-xl shadow-slate-200/60"><p className="text-xs font-black uppercase tracking-[0.2em] text-blue-600">Letron SSO</p><h1 className="mt-4 text-3xl font-black text-slate-950">Không thể đăng nhập</h1><p className="mt-3 text-sm leading-6 text-slate-500">{messages[code] ?? messages.login_failed}</p><div className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center"><Link className="rounded-xl bg-blue-600 px-5 py-3 text-sm font-bold text-white hover:bg-blue-700" href="/login">Thử lại</Link><Link className="rounded-xl border border-slate-300 px-5 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50" href="/">Về trang chính</Link></div></section></main>;
}
