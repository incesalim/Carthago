import Link from "next/link";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/credit", label: "Credit" },
  { href: "/deposits", label: "Deposits" },
  { href: "/asset-quality", label: "Asset Quality" },
  { href: "/capital", label: "Capital" },
  { href: "/profitability", label: "Profitability" },
  { href: "/sector/ratios", label: "Ratios" },
  { href: "/weekly", label: "Weekly" },
  { href: "/rates", label: "Rates" },
  { href: "/banks", label: "Banks" },
  { href: "/regulation", label: "Regulation" },
];

export default function Nav() {
  return (
    <nav className="sticky top-0 z-20 border-b border-neutral-200 bg-white/85 backdrop-blur supports-[backdrop-filter]:bg-white/70">
      <div className="flex flex-wrap items-center gap-1 px-8 py-3">
        <Link href="/" className="font-semibold mr-6 text-neutral-900 tracking-tight">
          🇹🇷 Banking Sector
        </Link>
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className="px-3 py-1.5 text-sm rounded-md text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900 transition-colors"
          >
            {t.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
