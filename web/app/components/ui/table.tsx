import * as React from "react";
import { cn } from "@/app/lib/cn";

function Table({
  className,
  wrapperClassName,
  ...props
}: React.ComponentProps<"table"> & { wrapperClassName?: string }) {
  return (
    <div className={cn("relative w-full overflow-x-auto", wrapperClassName)}>
      <table
        className={cn(
          "w-full caption-bottom border-collapse text-sm tabular-nums",
          className,
        )}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      className={cn("[&_tr]:border-b [&_tr]:border-border", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "border-b border-border transition-colors hover:bg-muted/50",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      className={cn(
        "h-9 px-3 text-left align-middle text-[11px] font-medium uppercase tracking-wide text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return <td className={cn("px-3 py-2 align-middle", className)} {...props} />;
}

const numTone = {
  neutral: "text-foreground",
  positive: "text-positive",
  negative: "text-negative",
  muted: "text-muted-foreground",
} as const;

/**
 * Numeric cell — right-aligned mono tabular figures, optionally tone-coloured
 * (the shared idiom for every data table; sign-based tone via `toneFor`).
 */
function TableCellNum({
  tone = "neutral",
  className,
  ...props
}: React.ComponentProps<"td"> & { tone?: keyof typeof numTone }) {
  return (
    <td
      className={cn(
        "px-3 py-2 text-right align-middle font-mono tabular-nums",
        numTone[tone],
        className,
      )}
      {...props}
    />
  );
}

/**
 * Sign → tone helper for TableCellNum: negatives red, everything else plain.
 * Deliberately does NOT green positives — on dense tables that's noise (and
 * "positive" isn't always good: CPI, costs). Pass tone="positive" explicitly
 * where a green really carries meaning (e.g. growth columns).
 */
function toneFor(v: number | null | undefined): keyof typeof numTone {
  if (v == null) return "muted";
  if (v < 0) return "negative";
  return "neutral";
}

export { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCellNum, toneFor };
