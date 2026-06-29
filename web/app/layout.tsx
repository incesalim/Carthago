import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Geist_Mono } from "next/font/google";
import "./globals.css";
import Nav from "./components/Nav";
import { RangeProvider } from "./components/range-context";
import { ThemeProvider } from "./components/ui/theme-provider";
import { Toaster } from "./components/ui/toaster";

// "Fresh / Flat" redesign uses Plus Jakarta Sans (geometric sans). The CSS
// variable name stays `--font-geist-sans` so globals.css's `--font-sans`
// mapping keeps working without churn elsewhere.
const geistSans = Plus_Jakarta_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
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
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
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
      </body>
    </html>
  );
}
