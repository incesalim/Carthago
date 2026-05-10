import Link from "next/link";

const pages = [
  { href: "/sector/ratios", title: "Key Ratios", desc: "NPL, CAR, ROA, ROE, LDR — sector KPI cards" },
  { href: "/sector", title: "Total Assets", desc: "Sector total-assets time series (75 months)" },
];

export default function Home() {
  return (
    <main className="p-8 max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Turkish Banking Sector Dashboard</h1>
      <p className="text-sm text-neutral-500 mb-8">
        Cloudflare Workers · D1 (Frankfurt) · OpenNext + Next.js
      </p>
      <ul className="space-y-3">
        {pages.map((p) => (
          <li key={p.href}>
            <Link
              href={p.href}
              className="block rounded-lg border bg-white p-4 hover:bg-neutral-50 transition"
            >
              <div className="font-medium">{p.title}</div>
              <div className="text-sm text-neutral-500">{p.desc}</div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
