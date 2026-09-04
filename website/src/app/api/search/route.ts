import { source } from "@/lib/source";
import { createFromSource } from "fumadocs-core/search/server";

export const revalidate = false;

/** `zh-CN` is not an Orama language; empty options keep the default tokenizer. */
export const { staticGET: GET } = createFromSource(source, {
  localeMap: {
    en: "english",
    "zh-CN": {},
  },
});
