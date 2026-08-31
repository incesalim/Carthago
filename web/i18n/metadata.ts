import type { Metadata } from "next";
import { getLocale } from "next-intl/server";
import { createText } from "./text";

/** Keep canonical URLs and robots rules unchanged; localize the visible metadata. */
export async function localizeMetadata(metadata: Metadata): Promise<Metadata> {
  const locale = await getLocale();
  const tx = createText(locale);
  const title = typeof metadata.title === "object" && metadata.title !== null
    ? Object.fromEntries(Object.entries(metadata.title).map(([key, value]) => [key, tx(value)])) as Metadata["title"]
    : tx(metadata.title);
  return {
    ...metadata,
    title,
    description: tx(metadata.description),
    ...(metadata.openGraph ? { openGraph: {
      ...metadata.openGraph,
      title: typeof metadata.openGraph.title === "string" ? tx(metadata.openGraph.title) : metadata.openGraph.title,
      description: tx(metadata.openGraph.description),
      locale: locale === "tr" ? "tr_TR" : "en_US",
      alternateLocale: locale === "tr" ? "en_US" : "tr_TR",
    }} : {}),
    ...(metadata.twitter ? { twitter: {
      ...metadata.twitter,
      title: typeof metadata.twitter.title === "string" ? tx(metadata.twitter.title) : metadata.twitter.title,
      description: tx(metadata.twitter.description),
    }} : {}),
  };
}
