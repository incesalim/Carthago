"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/app/lib/cn";
import { ThemeToggle } from "./ui/theme-toggle";
import logo from "@/public/logo.png";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/credit", label: "Credit" },
  { href: "/deposits", label: "Deposits" },
  { href: "/asset-quality", label: "Asset Quality" },
  { href: "/capital", label: "Capital" },
  { href: "/profitability", label: "Profitability" },
  { href: "/sector/ratios", label: "Ratios" },
  { href: "/weekly", label: "Weekly" },
  { href: "/liquidity", label: "Liquidity" },
  { href: "/digital", label: "Digital" },
  { href: "/funds", label: "Funds" },
  { href: "/economy", label: "Economy" },
  { href: "/rates", label: "Rates" },
  { href: "/banks", label: "Banks" },
  { href: "/cross-bank", label: "Compare" },
  { href: "/ownership", label: "Ownership" },
  { href: "/regulation", label: "Regulation" },
  { href: "/news", label: "News" },
  { href: "/pipeline", label: "Pipeline" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function Nav() {
  const pathname = usePathname() ?? "/";

  return (
    <nav className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/65">
      <div className="flex items-center gap-2 px-4 py-2.5 sm:px-6 lg:px-8">
        <Link
          href="/"
          aria-label="Carthago — home"
          className="mr-2 flex shrink-0 items-center gap-2 text-foreground"
        >
          <Image
            src={logo}
            alt=""
            width={28}
            height={28}
            priority
            unoptimized
            className="size-7 shrink-0 object-contain dark:brightness-0 dark:invert"
          />
          <span className="hidden flex-col leading-none sm:flex">
            <span className="text-[15px] font-semibold tracking-tight">Carthago</span>
            <span className="mt-0.5 hidden text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground lg:block">
              Turkish Banking Sector
            </span>
          </span>
        </Link>

        <div className="flex flex-1 flex-wrap items-center gap-0.5">
          {TABS.map((t) => {
            const active = isActive(pathname, t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                {t.label}
              </Link>
            );
          })}
        </div>

        <ThemeToggle className="ml-auto shrink-0" />
      </div>
    </nav>
  );
}
