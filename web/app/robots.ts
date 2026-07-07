import type { MetadataRoute } from "next";

// Tell crawlers the whole site is fair game except the password-gated admin
// panel and the internal API routes (neither is indexable content), and point
// them at the generated sitemap. Helps search + URL-categorization vendors
// (why a young domain reads as "uncategorized" until they crawl it).
const BASE = "https://carthago.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin", "/api/"],
    },
    sitemap: `${BASE}/sitemap.xml`,
  };
}
