import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";
import { notFound } from "next/navigation";
import { i18nProvider } from "fumadocs-ui/i18n";
import { SiteProvider } from "@/components/site-provider";
import { i18n, isSiteLocale } from "@/lib/i18n";
import { translations } from "@/lib/layout.shared";
import "../global.css";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-newsreader" });

export const metadata: Metadata = {
  title: { default: "BORA Docs", template: "%s · BORA Docs" },
  description:
    "BORA — Bounded Orchestration for Runtime Agents: lock, bounded Attempts, visibility, ACP inlets, and independent evaluation.",
};

export function generateStaticParams() {
  return i18n.languages.map((lang) => ({ lang }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isSiteLocale(lang)) notFound();

  return (
    <html
      lang={lang}
      className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable}`}
      suppressHydrationWarning
    >
      <body className="flex min-h-screen flex-col antialiased">
        <SiteProvider i18n={i18nProvider(translations, lang)}>{children}</SiteProvider>
      </body>
    </html>
  );
}
