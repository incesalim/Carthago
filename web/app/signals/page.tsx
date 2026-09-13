import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const metadata = { robots: { index: false, follow: false } };

/** Compatibility link only; observations are rendered behind the admin gate. */
export default function SignalsRedirect() {
  redirect("/admin/signals");
}
