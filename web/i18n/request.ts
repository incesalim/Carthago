import { cookies } from "next/headers";
import { getRequestConfig } from "next-intl/server";
import { LOCALE_COOKIE, resolveLocale } from "./config";

export default getRequestConfig(async () => {
  const store = await cookies();
  return {
    locale: resolveLocale(store.get(LOCALE_COOKIE)?.value),
    timeZone: "Europe/Istanbul",
    messages: {},
  };
});
