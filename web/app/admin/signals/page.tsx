import { getLocale } from "next-intl/server";
import { redirect } from "next/navigation";
import { AdminAuthError, requireAdmin } from "../../lib/admin-auth";
import { loadSignalSnapshot } from "../../lib/sector-signals";
import SignalsView from "./SignalsView";

export const dynamic = "force-dynamic";
export async function generateMetadata() {
  const tr = await getLocale() === "tr";
  return {
    title: tr ? "Sinyaller" : "Signals",
    robots: { index: false, follow: false },
    description: tr ? "Bankacılık verilerinden araştırma sinyalleri, gözlemler ve değerlendirme koşulları." : "Research signals from banking data, with observations and evaluation criteria.",
  };
}

export default async function SignalsPage() {
  // Authorize before starting any data work or serializing observations to RSC.
  try {
    await requireAdmin();
  } catch (error) {
    if (error instanceof AdminAuthError) redirect("/admin");
    throw error;
  }
  const [snapshot, locale] = await Promise.all([loadSignalSnapshot(), getLocale()]);
  return <SignalsView snapshot={snapshot} locale={locale} />;
}
