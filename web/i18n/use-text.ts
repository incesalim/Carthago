import { useLocale } from "next-intl";
import { createText } from "./text";

/** next-intl supplies request-scoped locale on the server and context on clients. */
export function useText() {
  return createText(useLocale());
}
