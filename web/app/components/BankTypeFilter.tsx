"use client";

import { useText } from "@/i18n/use-text";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { ScrollX } from "@/app/components/ui/scroll-x";

// Order: Sector, then the deposit-ownership trio State / Domestic / Foreign,
// then Participation and Dev & Inv. "Domestic" (10005 = Yerli Özel) reads
// clearer than "Private" alongside Foreign (both are non-state/private).
//
// Drives the "Table-15 scorecard by bank type" section on Overview via a `?type=`
// search param; the sector default omits the param entirely.
const OPTIONS = [
  { code: "10001", label: "Sector" },
  { code: "10006", label: "State" },
  { code: "10005", label: "Domestic" },
  { code: "10007", label: "Foreign" },
  { code: "10003", label: "Participation" },
  { code: "10004", label: "Dev & Inv" },
];

export default function BankTypeFilter({ active }: { active: string }) {
  const tx = useText();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function select(code: string) {
    const next = new URLSearchParams(params);
    if (code === "10001") next.delete("type"); // default = sector → omit param
    else next.set("type", code);
    const qs = next.toString();
    // Keep the scorecard in view across the re-render instead of jumping to the top.
    router.push(qs ? `${pathname}?${qs}#by-type` : `${pathname}#by-type`, {
      scroll: false,
    });
  }

  // The Desk's control register: mono-caps text with an ink underline on the
  // active tab — no pill, no fill, no blue (blue is a verb; this navigates
  // nothing, it switches what the band below is showing).
  //
  // Turkish makes the last label ("Kalkınma ve Yatırım") long enough that
  // wrapping orphans it on its own row. Keep the register on one line and let
  // it scroll; hovering or tabbing to a clipped tab brings its full name in.
  return (
    <ScrollX
      className="min-w-0 max-w-full"
      innerClassName="flex flex-nowrap gap-px"
      label={tx("Bank group filter — scrolls horizontally")}
    >
      {OPTIONS.map((o) => (
        <button
          key={o.code}
          onClick={() => select(o.code)}
          onMouseEnter={(event) => event.currentTarget.scrollIntoView({ block: "nearest", inline: "nearest" })}
          onFocus={(event) => event.currentTarget.scrollIntoView({ block: "nearest", inline: "nearest" })}
          aria-pressed={active === o.code}
          style={{ scrollMarginInline: 34 }}
          className={`shrink-0 whitespace-nowrap border-b-2 px-2 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.07em] transition-colors ${
            active === o.code
              ? "border-foreground font-semibold text-foreground"
              : "border-transparent text-faint hover:text-foreground"
          }`}
        >
          {tx(o.label)}
        </button>
      ))}
    </ScrollX>
  );
}
