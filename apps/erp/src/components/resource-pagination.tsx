import Link from "next/link";

export function ResourcePagination({ basePath, page, hasNext, tone = "blue" }: Readonly<{ basePath: string; page: number; hasNext: boolean; tone?: "blue" | "emerald" }>) {
  const activeClass = tone === "emerald" ? "border-emerald-200 text-emerald-700 hover:bg-emerald-50" : "border-blue-200 text-blue-700 hover:bg-blue-50";
  return <div className="flex items-center justify-between border-t p-4 text-sm"><span className="text-muted-foreground">Trang {page}</span><div className="flex items-center gap-2">{page > 1 ? <Link className={`rounded-md border px-3 py-1.5 font-medium ${activeClass}`} href={`${basePath}?page=${page - 1}`}>Trước</Link> : null}{hasNext ? <Link className={`rounded-md border px-3 py-1.5 font-medium ${activeClass}`} href={`${basePath}?page=${page + 1}`}>Tiếp</Link> : null}</div></div>;
}
