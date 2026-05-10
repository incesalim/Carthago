import Link from "next/link";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/credit", label: "Credit" },
  { href: "/deposits", label: "Deposits" },
  { href: "/asset-quality", label: "Asset Quality" },
  { href: "/capital", label: "Capital" },
  { href: "/profitability", label: "Profitability" },
  { href: "/weekly", label: "Weekly" },
  { href: "/rates", label: "Rates" },
];

export default function Nav() {
  return (
    <nav className="border-b bg-white">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center gap-1 px-6 py-3">
        <Link href="/" className="font-semibold mr-6 text-neutral-900">
          🇹🇷 Banking Sector
        </Link>
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="px-3 py-1.5 text-sm rounded-md text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 transition"
          >
            {t.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
