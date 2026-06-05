"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";

// Order: Sector, then the deposit-ownership trio State / Domestic / Foreign,
// then Participation and Dev & Inv. "Domestic" (10005 = Yerli Özel) reads
// clearer than "Private" alongside Foreign (both are non-state/private).
const OPTIONS = [
  { code: "10001", label: "Sector" },
  { code: "10006", label: "State" },
  { code: "10005", label: "Domestic" },
  { code: "10007", label: "Foreign" },
  { code: "10003", label: "Participation" },
  { code: "10004", label: "Dev & Inv" },
];

export default function BankTypeFilter({ active }: { active: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function select(code: string) {
    const next = new URLSearchParams(params);
    if (code === "10001") next.delete("type"); // default = sector → omit param
    else next.set("type", code);
    const qs = next.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg border bg-muted p-1">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => select(o.code)}
          className={`px-3 py-1.5 text-sm rounded-md transition ${
            active === o.code
              ? "bg-card shadow-sm font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
