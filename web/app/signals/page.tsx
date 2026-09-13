import { getLocale } from "next-intl/server";
import { loadSignalSnapshot } from "../lib/sector-signals";
import SignalsView from "./SignalsView";

export const dynamic = "force-dynamic";
export async function generateMetadata() {
  const tr = await getLocale() === "tr";
  return {
    title: tr ? "Sinyaller" : "Signals",
    description: tr ? "Bankacılık verilerinden araştırma sinyalleri, gözlemler ve değerlendirme koşulları." : "Research signals from banking data, with observations and evaluation criteria.",
  };
}

export default async function SignalsPage() {
  const [snapshot, locale] = await Promise.all([loadSignalSnapshot(), getLocale()]);
  return <SignalsView snapshot={snapshot} locale={locale} />;
}
