import type { Metadata } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";
import Nav from "./components/Nav";
import Beacon from "./components/Beacon";
import { RangeProvider } from "./components/range-context";
import { ThemeProvider } from "./components/ui/theme-provider";
import { Toaster } from "./components/ui/toaster";

// "Editorial" redesign: role-based typography. Plex Sans = body, Source Serif
// 4 = headings (font-serif), Plex Mono = labels + all numbers (font-mono). The
// CSS variable names stay `--font-geist-sans`/`--font-geist-mono` so globals.css
// keeps mapping `--font-sans`/`--font-mono` without churn; serif is new.
const geistSans = IBM_Plex_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const geistMono = IBM_Plex_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://carthago.app"),
  title: {
    default: "Carthago · Turkish Banking Sector",
    template: "%s · Carthago",
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

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${sourceSerif.variable} h-full`}
    >
      <body className="min-h-full bg-background font-sans text-foreground antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <RangeProvider>
            <div className="flex min-h-full flex-col lg:flex-row">
              <Nav />
              <div className="min-w-0 flex-1">{children}</div>
            </div>
          </RangeProvider>
          <Toaster />
        </ThemeProvider>
        <Beacon />
      </body>
    </html>
  );
}
