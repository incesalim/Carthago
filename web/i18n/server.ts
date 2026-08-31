import { getLocale } from "next-intl/server";
import { createText } from "./text";

export async function getText() {
  return createText(await getLocale());
}
