"use client";

import type { ReactNode } from "react";
import { RootProvider, type RootProviderProps } from "fumadocs-ui/provider/next";
import { StaticSearchDialog } from "@/components/static-search";
import { siteBasePath } from "@/lib/shared";

type SiteProviderProps = {
  children: ReactNode;
  i18n: NonNullable<RootProviderProps["i18n"]>;
};

/**
 * Owns browser-only Fumadocs providers and locale changes.
 *
 * Locale routes are root layouts because they set the document language. A
 * full navigation lets Next.js replace that root cleanly and prevents the
 * theme bootstrap script from being rendered inside a client transition.
 *
 * Search runs on the exported index in the browser (`output: "export"`).
 */
export function SiteProvider({ children, i18n }: SiteProviderProps) {
  return (
    <RootProvider
      search={{ SearchDialog: StaticSearchDialog }}
      i18n={{
        ...i18n,
        onLocaleChange(locale) {
          const url = new URL(window.location.href);
          const base = siteBasePath();
          let path = url.pathname;
          if (base && path.startsWith(base)) path = path.slice(base.length) || "/";
          const segments = path.split("/");
          segments[1] = locale;
          url.pathname = `${base}${segments.join("/")}`;
          window.location.assign(url);
        },
      }}
    >
      {children}
    </RootProvider>
  );
}
