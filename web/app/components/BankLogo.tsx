/**
 * BankLogo — a bank's brand mark, rendered at a fixed height on a white chip.
 *
 * Logos are a mix of square marks and wide wordmarks (see web/public/logos/,
 * sourced by scripts/fetch_bank_logos.py). Rendering every one at a fixed
 * HEIGHT with natural width keeps both legible and lets them line up as a row.
 * The white chip gives full-colour marks a consistent, dark-mode-safe backdrop.
 *
 * Tickers without a committed logo (a short tail of small/obscure banks) fall
 * back to a neutral ticker chip — no broken-image request. Membership +
 * intrinsic dimensions come from the generated manifest, so the component never
 * guesses a size or points at a missing file.
 */
import Image from "next/image";
import { BANK_LOGOS } from "@/app/lib/bank-logos.generated";
import { cn } from "@/app/lib/cn";

export function hasBankLogo(ticker: string): boolean {
  return ticker.toUpperCase() in BANK_LOGOS;
}

interface Props {
  ticker: string;
  /** Rendered logo height in px (chip is a touch taller). Default 20. */
  height?: number;
  /** Bank name, used for the image alt / placeholder title. */
  name?: string;
  className?: string;
}

export default function BankLogo({ ticker, height = 20, name, className }: Props) {
  const t = ticker.toUpperCase();
  const dims = BANK_LOGOS[t];
  const chipH = height + 8;
  // Cap width so a wide wordmark can't crowd out the surrounding layout; a
  // very wide mark then contains to a shorter height (still legible).
  const maxW = Math.round(height * 6);
  const chip =
    "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-md " +
    "bg-white ring-1 ring-black/10 dark:ring-white/10";

  if (!dims) {
    return (
      <span
        className={cn(chip, "font-mono font-semibold text-neutral-400", className)}
        style={{ height: chipH, minWidth: chipH, paddingInline: 5, fontSize: Math.round(height * 0.34) }}
        title={name ?? t}
        aria-hidden
      >
        {t.slice(0, 4)}
      </span>
    );
  }

  const [w, h] = dims;
  return (
    <span className={cn(chip, className)} style={{ height: chipH, paddingInline: 5 }}>
      <Image
        src={`/logos/${t}.png`}
        alt={name ? `${name} logo` : `${t} logo`}
        width={w}
        height={h}
        unoptimized
        className="object-contain"
        style={{ height, width: "auto", maxWidth: maxW }}
      />
    </span>
  );
}
