export function larkLoginHref(returnTo: string): string {
  const query = new URLSearchParams({ return_to: returnTo });
  return `/api/auth/login?${query.toString()}`;
}

export function redirectToLarkLogin(returnTo?: string): void {
  if (typeof window === "undefined") return;
  window.top?.location.replace(
    larkLoginHref(
      returnTo ?? `${window.location.pathname}${window.location.search}`,
    ),
  );
}
