import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { isSiteLocale } from "@/lib/i18n";
import "@/components/landing/landing.css";

export default async function Layout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!isSiteLocale(lang)) notFound();

  return children;
}
