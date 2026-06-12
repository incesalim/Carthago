// Shared status presentation for the coverage matrix. Pure constants (no server
// imports) so both client components can use them. Status values come from
// scripts/sync_audit_expected.py: not_expected | missing | error | manual | ok.
import type { BadgeProps } from "@/app/components/ui";

type Variant = NonNullable<BadgeProps["variant"]>;

export const STATUS_VARIANT: Record<string, Variant> = {
  ok: "positive",
  manual: "info",
  error: "negative",
  missing: "warning",
  not_expected: "secondary",
};

export const STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  manual: "Manual",
  error: "Error",
  missing: "Missing",
  not_expected: "N/A",
};

// Compact cell tint + glyph for the dense grid.
export const STATUS_CELL: Record<string, { cls: string; glyph: string }> = {
  ok: { cls: "bg-positive/15 text-positive", glyph: "✓" },
  manual: { cls: "bg-info/15 text-info", glyph: "✎" },
  error: { cls: "bg-negative/25 text-negative font-semibold", glyph: "!" },
  missing: { cls: "bg-warning/15 text-warning", glyph: "·" },
  not_expected: { cls: "bg-muted text-muted-foreground", glyph: "" },
};

export const STATUSES = ["ok", "manual", "error", "missing", "not_expected"] as const;
