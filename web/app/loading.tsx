/**
 * Route-level loading UI. Pages are `force-dynamic` and query D1 at render, so
 * navigation shows this skeleton (header + KPI strip + chart grid) until the
 * server component streams in. Covers every tab unless a segment overrides it.
 */
import { Skeleton } from "@/app/components/ui";

export default function Loading() {
  return (
    <main className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      {/* Header */}
      <div className="flex items-end justify-between gap-3">
        <div className="space-y-2">
          <Skeleton className="h-7 w-44" />
          <Skeleton className="h-4 w-80 max-w-[70vw]" />
        </div>
        <Skeleton className="h-6 w-36 rounded-full" />
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-lg" />
        ))}
      </div>

      {/* Chart grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-[320px] rounded-lg" />
        ))}
      </div>
    </main>
  );
}
