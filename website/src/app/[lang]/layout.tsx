import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Anton, Geist, Geist_Mono, Noto_Sans_SC } from "next/font/google";
import { notFound } from "next/navigation";
import { i18nProvider } from "fumadocs-ui/i18n";
import { SiteProvider } from "@/components/site-provider";
import { i18n, isSiteLocale } from "@/lib/i18n";
import { translations } from "@/lib/layout.shared";
import "../global.css";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const anton = Anton({ weight: "400", subsets: ["latin"], variable: "--font-anton" });
const notoSansSC = Noto_Sans_SC({
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  variable: "--font-noto-sans-sc",
});

export const metadata: Metadata = {
  title: { default: "ageval Docs", template: "%s · ageval Docs" },
  description:
    "ageval — lock a dataset, open a box, run the task, let an independent evaluator own the score.",
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
      className={`${geistSans.variable} ${geistMono.variable} ${anton.variable} ${notoSansSC.variable}`}
      suppressHydrationWarning
    >
      <body className="flex min-h-screen flex-col antialiased">
        <SiteProvider i18n={i18nProvider(translations, lang)}>{children}</SiteProvider>
      </body>
    </html>
  );
}
