import Link from "next/link";

import { Button } from "@/components/ui/button";

export function AuthErrorActions({ loginHref }: { loginHref: string }) {
  return (
    <div className="mt-4">
      <Button asChild size="sm">
        <Link href={loginHref} target="_top" rel="noopener">
          Đăng nhập lại bằng Lark
        </Link>
      </Button>
    </div>
  );
}
