export function larkLoginHref(returnTo: string): string {
  const query = new URLSearchParams({ return_to: returnTo });
  return `/api/auth/login?${query.toString()}`;
}
