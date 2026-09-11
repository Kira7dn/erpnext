"use client";

import { larkLoginHref } from "@/lib/auth-navigation";

export function ClientAuthRecovery() {
  return (
    <a
      className="mt-3 block w-fit underline"
      href="/api/auth/login"
      onClick={(event) => {
        event.preventDefault();
        window.top?.location.assign(
          larkLoginHref(`${window.location.pathname}${window.location.search}`),
        );
      }}
    >
      Đăng nhập lại bằng Lark
    </a>
  );
}
