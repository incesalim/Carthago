import type { Metadata } from "next";
import { Instrument_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import Nav from "./components/Nav";
import Beacon from "./components/Beacon";
import GoogleAnalytics from "./components/GoogleAnalytics";
import { RangeProvider } from "./components/range-context";
import { ThemeProvider } from "./components/ui/theme-provider";
import { Toaster } from "./components/ui/toaster";

// "The Desk" typography: Instrument Sans (variable) carries both body and
// display — hierarchy comes from weight/size, not a second family. Plex Mono
// = labels + every figure. The CSS variable names stay
// `--font-geist-sans`/`--font-geist-mono` so globals.css keeps mapping
// `--font-sans`/`--font-mono` without churn; `--font-serif` now resolves to
// the sans stack (the Desk has no serif register).
const geistSans = Instrument_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = IBM_Plex_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://carthago.app"),
  title: {
    default: "Carthago · Turkish Banking Sector",
    // Brand first: a browser tab truncates to ~15 chars, so leading with the
    // page name made every tab read as a clipped "Turkish Banking Regu…".
    // The page name still follows for search results and shared links.
    template: "Carthago · %s",
  },
  description:
    "Carthago — Turkish banking sector & economy dashboard. BDDK monthly + weekly aggregates on Cloudflare D1.",
  openGraph: {
    type: "website",
    siteName: "Carthago",
    title: "Carthago · Turkish Banking Sector",
    description:
      "Turkish banking sector & economy dashboard — BDDK monthly + weekly aggregates, audited bank financials, and macro series.",
    url: "https://carthago.app",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "Carthago · Turkish Banking Sector",
    description:
      "Turkish banking sector & economy dashboard — BDDK monthly + weekly aggregates, audited bank financials, and macro series.",
  },
};

// Site-wide structured data. Organization + WebSite give search engines an
// explicit identity for the site (name, publisher, canonical URL) instead of
// inferring it — the same signals that help URL-categorization vendors and
// improve how the site is represented in results.
const orgJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Carthago",
  url: "https://carthago.app",
  description:
    "Data and analytics on the Turkish banking sector — audited BRSA bank financials, BDDK aggregates and macro context.",
  logo: "https://carthago.app/icon.png",
};

const siteJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Carthago · Turkish Banking Sector",
  url: "https://carthago.app",
  inLanguage: "en",
  about: "Turkish banking sector data and analytics",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(orgJsonLd) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(siteJsonLd) }}
        />
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <RangeProvider>
            <div className="flex min-h-full flex-col lg:flex-row">
              <Nav />
              {/* The document sheet: page content renders on a white sheet
                  floating on the workspace ground (desktop); below lg the
                  sheet goes full-bleed. */}
              <div className="min-w-0 flex-1 lg:py-5 lg:pl-2 lg:pr-6">
                <div className="min-h-full bg-card lg:rounded-[10px] lg:border lg:border-border lg:shadow-sheet">
                  {children}
                </div>
              </div>
            </div>
          </RangeProvider>
          <Toaster />
        </ThemeProvider>
        <Beacon />
        <GoogleAnalytics />
      </body>
    </html>
  );
}
