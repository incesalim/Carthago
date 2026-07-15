"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, ChevronRight, Menu, X } from "lucide-react";
import { cn } from "@/app/lib/cn";
import { ThemeToggle } from "./ui/theme-toggle";

type NavChild = { href: string; label: string };
type NavItem = { href: string; label: string; children?: NavChild[] };
type NavSection = { id: string; label?: string; items: NavItem[] };

const SECTIONS: NavSection[] = [
  {
    id: "sector",
    label: "Sector",
    items: [
      // FSR story order (spine S1→S7): size → credit → funding → liquidity →
      // asset quality → solvency → earnings. Digital lives under Markets &
      // Macro (structure/context, not a CAMELS vital — audit: relocate).
      { href: "/", label: "Overview" },
      { href: "/credit", label: "Credit" },
      { href: "/deposits", label: "Deposits" },
      { href: "/liquidity", label: "Liquidity" },
      { href: "/asset-quality", label: "Asset Quality" },
      { href: "/capital", label: "Capital" },
      { href: "/profitability", label: "Profitability" },
    ],
  },
  {
    id: "banks",
    label: "By Bank",
    items: [
      { href: "/banks", label: "Banks" },
      { href: "/cross-bank", label: "Compare" },
      { href: "/ownership", label: "Ownership" },
      { href: "/actions", label: "Actions" },
    ],
  },
  {
    id: "markets",
    label: "Markets & Macro",
    items: [
      { href: "/rates", label: "Rates" },
      { href: "/market-risk", label: "Market Risk" },
      { href: "/funds", label: "Funds" },
      { href: "/digital", label: "Digital" },
      {
        href: "/non-bank",
        label: "Non-Bank",
        children: [
          { href: "/non-bank", label: "Overview" },
          { href: "/non-bank/share-of-banking", label: "Share of Banking" },
        ],
      },
      {
        href: "/economy",
        label: "Economy",
        children: [
          { href: "/economy/economic-growth", label: "Economic Growth" },
          { href: "/economy/balance-of-payments", label: "Balance of Payments" },
          { href: "/economy/budget", label: "Budget" },
          { href: "/economy/inflation", label: "Inflation" },
          { href: "/economy/foreign-trade", label: "Foreign Trade" },
        ],
      },
    ],
  },
  {
    id: "more",
    label: "More",
    items: [
      { href: "/regulation", label: "Regulation" },
      {
        href: "/news",
        label: "News",
        children: [
          { href: "/news", label: "Sector Press" },
          { href: "/news/google", label: "Google News" },
        ],
      },
      { href: "/pipeline", label: "Pipeline" },
      { href: "/admin", label: "Admin" },
    ],
  },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

// True when the current route is the section root or any page beneath it.
function inSection(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Brand() {
  return (
    <Link
      href="/"
      aria-label="Carthago — home"
      className="flex shrink-0 items-center gap-2 text-foreground"
    >
      {/* The compass has navy elements that sink into the dark sheet, so dark
          mode swaps to a tonally-lifted variant of the same mark. Both are
          transparent — no box on either ground. */}
      <Image
        src="/logo.png"
        alt=""
        width={28}
        height={28}
        priority
        unoptimized
        className="size-7 shrink-0 object-contain dark:hidden"
      />
      <Image
        src="/logo-dark.png"
        alt=""
        width={28}
        height={28}
        priority
        unoptimized
        className="hidden size-7 shrink-0 object-contain dark:block"
      />
      <span className="flex flex-col leading-none">
        <span className="text-lg font-bold tracking-tight">Carthago</span>
        <span className="mt-0.5 text-[10px] font-medium text-faint">
          Turkish banking data
        </span>
      </span>
    </Link>
  );
}

function NavLinks({
  pathname,
  onNavigate,
}: {
  pathname: string;
  onNavigate?: () => void;
}) {
  // Explicit per-group expand overrides; absent groups fall back to "open when
  // the current route is inside the section".
  const [openGroups, setOpenGroups] = React.useState<Record<string, boolean>>({});

  const toggleGroup = (href: string) =>
    setOpenGroups((prev) => ({
      ...prev,
      [href]: !(prev[href] ?? inSection(pathname, href)),
    }));

  const renderItem = (t: NavItem) => {
    if (!t.children) {
      const active = isActive(pathname, t.href);
      return (
        <Link
          key={t.href}
          href={t.href}
          aria-current={active ? "page" : undefined}
          onClick={onNavigate}
          className={cn(
            // Quiet rail: plain text, no hover fill; the active route gets an
            // ink bar on the left and full ink — nothing else competes.
            "border-l-2 px-3 py-1 text-[13px] transition-colors",
            active
              ? "border-foreground font-semibold text-foreground"
              : "border-transparent font-normal text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </Link>
      );
    }

    const sectionActive = inSection(pathname, t.href);
    const parentActive = pathname === t.href;
    const isOpen = openGroups[t.href] ?? sectionActive;

    return (
      <div key={t.href}>
        <div className="flex items-center gap-1">
          <Link
            href={t.href}
            aria-current={parentActive ? "page" : undefined}
            onClick={onNavigate}
            className={cn(
              "flex-1 border-l-2 px-3 py-1 text-[13px] transition-colors",
              parentActive
                ? "border-foreground font-semibold text-foreground"
                : sectionActive
                  ? "border-transparent text-foreground"
                  : "border-transparent font-normal text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
          <button
            type="button"
            aria-label={`${isOpen ? "Collapse" : "Expand"} ${t.label} section`}
            aria-expanded={isOpen}
            onClick={() => toggleGroup(t.href)}
            className="inline-flex size-6 shrink-0 items-center justify-center text-faint transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {isOpen ? (
              <ChevronDown className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        </div>

        {isOpen && (
          <div className="mt-0.5 ml-4 flex flex-col gap-0.5">
            {t.children.map((c) => {
              const childActive = isActive(pathname, c.href);
              return (
                <Link
                  key={c.href}
                  href={c.href}
                  aria-current={childActive ? "page" : undefined}
                  onClick={onNavigate}
                  className={cn(
                    "border-l-2 px-3 py-0.5 text-[12px] transition-colors",
                    childActive
                      ? "border-foreground font-semibold text-foreground"
                      : "border-transparent font-normal text-muted-foreground hover:text-foreground",
                  )}
                >
                  {c.label}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <nav
      aria-label="Primary"
      className="flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-2"
    >
      {SECTIONS.map((section, i) => (
        <div
          key={section.id}
          className={cn("flex flex-col gap-0.5", i > 0 && "mt-2")}
        >
          {section.label && (
            // Mono-caps group label — the rail's only ornament.
            <div className="px-3 pb-1.5 font-mono text-[9px] font-medium uppercase tracking-[0.12em] text-faint">
              {section.label}
            </div>
          )}
          {section.items.map(renderItem)}
        </div>
      ))}
    </nav>
  );
}

export default function Nav() {
  const pathname = usePathname() ?? "/";
  const [open, setOpen] = React.useState(false);

  // Close the mobile drawer whenever the route changes.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  React.useEffect(() => setOpen(false), [pathname]);

  // Lock background scroll while the mobile drawer is open.
  React.useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  return (
    <>
      {/* Desktop rail — sits directly on the workspace ground; the sheet's own
          edge provides the separation, so the rail carries no border or fill. */}
      <aside className="sticky top-0 z-30 hidden h-screen w-52 shrink-0 flex-col bg-background lg:flex">
        <div className="px-6 pb-2 pt-5">
          <Brand />
        </div>
        <NavLinks pathname={pathname} />
        <div className="mx-6 border-t border-border px-0 py-3">
          <ThemeToggle />
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between gap-2 border-b border-border bg-background px-4 py-2.5 lg:hidden">
        <Brand />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <button
            type="button"
            aria-label="Open navigation menu"
            aria-expanded={open}
            onClick={() => setOpen(true)}
            className="inline-flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Menu className="size-5" />
          </button>
        </div>
      </header>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-foreground/20 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 flex w-64 max-w-[80%] flex-col border-r border-border bg-background shadow-xl">
            <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
              <Brand />
              <button
                type="button"
                aria-label="Close navigation menu"
                onClick={() => setOpen(false)}
                className="inline-flex size-9 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <X className="size-5" />
              </button>
            </div>
            <NavLinks pathname={pathname} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}
    </>
  );
}
