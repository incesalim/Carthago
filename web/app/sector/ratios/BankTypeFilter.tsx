"use client";

import { useRouter, useSearchParams, usePathname } from "next/navigation";

const OPTIONS = [
  { code: "10001", label: "Sector" },
  { code: "10005", label: "Private" },
  { code: "10006", label: "State" },
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
    <div className="inline-flex flex-wrap gap-1 rounded-lg border bg-neutral-50 p-1">
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => select(o.code)}
          className={`px-3 py-1.5 text-sm rounded-md transition ${
            active === o.code
              ? "bg-white shadow-sm font-medium text-neutral-900"
              : "text-neutral-600 hover:text-neutral-900"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
