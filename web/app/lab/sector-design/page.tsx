import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { loadDesignData } from "./data";
import SectorDesign from "./SectorDesign";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "Sector design studies",
  robots: { index: false, follow: false },
};

export default async function SectorDesignPage() {
  // Design studies are local artifacts, never a public product route.
  if (process.env.NODE_ENV !== "development") notFound();
  return <SectorDesign data={await loadDesignData()} />;
}
