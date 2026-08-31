import type { ReactNode } from "react";

// Operator tools keep their English terminology even when the public-site
// preference is Turkish. Announce that boundary to assistive technology.
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <div lang="en">{children}</div>;
}
