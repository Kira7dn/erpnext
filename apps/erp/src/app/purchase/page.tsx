import Link from "next/link";

const cards = [
  {
    code: "PUR-01",
    title: "Nhà cung cấp",
    description: "Quản lý Supplier cùng Contact và Address trong một context.",
    href: "/purchase/suppliers",
  },
  {
    code: "PUR-02",
    title: "Vật tư / Item",
    description: "Tạo và cập nhật Item theo metadata ERPNext cho nghiệp vụ mua hàng.",
    href: "/purchase/items",
  },
  {
    code: "PUR-03",
    title: "Material Request",
    description: "Tạo request với Item và Supplier; hệ thống tạo RFQ cùng orchestration.",
    href: "/purchase/requests",
  },
  {
    code: "PUR-04",
    title: "Warehouse",
    description: "Chọn và quản lý kho dùng cho Purchase Receipt.",
    href: "/purchase/warehouses",
  },
  {
    code: "PUR-05",
    title: "Purchase Receipt",
    description: "Tiếp nhận hàng từ Purchase Order đã Submit.",
    href: "/purchase/receipts",
  },
] as const;

export default function PurchaseHomePage() {
  return (
    <main className="mx-auto max-w-7xl space-y-8 p-5 md:p-8">
      <div>
        <div className="mb-2 text-xs font-bold uppercase tracking-[0.16em] text-violet-700">
          LeTRON-Mua hàng / Purchase
        </div>
        <h1 className="text-3xl font-bold tracking-tight">Mua hàng</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Truy cập nhanh các màn hình nghiệp vụ Purchase của LeTRON.
        </p>
      </div>
      <section aria-label="Các màn hình Purchase" className="grid gap-5 md:grid-cols-3">
        {cards.map((card) => (
          <Link
            className="group rounded-xl border bg-card p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-md"
            href={card.href}
            key={card.href}
          >
            <div className="text-xs font-bold uppercase tracking-[0.16em] text-violet-700">
              {card.code}
            </div>
            <h2 className="mt-3 text-xl font-semibold group-hover:text-violet-700">
              {card.title}
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {card.description}
            </p>
            <span className="mt-5 inline-block text-sm font-medium text-violet-700">
              Mở màn hình →
            </span>
          </Link>
        ))}
      </section>
    </main>
  );
}
