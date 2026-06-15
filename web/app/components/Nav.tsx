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
          className="mr-2 flex shrink-0 items-center gap-2 font-semibold tracking-tight text-foreground"
        >
          <span className="grid size-7 shrink-0 place-items-center overflow-hidden rounded-md bg-white ring-1 ring-border">
            <Image
              src={logo}
              alt=""
              width={28}
              height={28}
              priority
              unoptimized
              className="size-full object-contain"
            />
          </span>
          <span className="hidden sm:inline">Banking Sector</span>
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
