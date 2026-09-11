import { Button } from "@/components/ui/button";

export function AuthErrorActions({ loginHref }: { loginHref: string }) {
  return (
    <div className="mt-4">
      <Button asChild size="sm">
        <a href={loginHref} target="_top" rel="noopener">
          Đăng nhập lại bằng Lark
        </a>
      </Button>
    </div>
  );
}
