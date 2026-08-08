"use client";

import type { ReactNode } from "react";
import { RootProvider, type RootProviderProps } from "fumadocs-ui/provider/next";

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
 */
export function SiteProvider({ children, i18n }: SiteProviderProps) {
  return (
    <RootProvider
      i18n={{
        ...i18n,
        onLocaleChange(locale) {
          const url = new URL(window.location.href);
          const segments = url.pathname.split("/");
          segments[1] = locale;
          url.pathname = segments.join("/");
          window.location.assign(url);
        },
      }}
    >
      {children}
    </RootProvider>
  );
}
