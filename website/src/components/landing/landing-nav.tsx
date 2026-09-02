"use client";

import { useRef } from "react";
import Link from "next/link";
import { OwlFlatIcon } from "@/components/owl-flat";
import type { SiteLocale } from "@/lib/i18n";
import type { LandingCopy } from "./copy";

type LandingNavProps = {
  lang: SiteLocale;
  copy: LandingCopy["nav"];
  navAria: string;
  repoUrl: string;
};

const anchors = [
  ["problem", "problem"],
  ["environment", "environment"],
  ["eval", "eval"],
  ["plugin", "plugin"],
  ["faq", "faq"],
  ["docs", "docs"],
] as const;

export function LandingNav({ lang, copy, navAria, repoUrl }: LandingNavProps) {
  const drawerRef = useRef<HTMLDetailsElement>(null);
  const otherLang = lang === "zh-CN" ? "en" : "zh-CN";

  function closeDrawer() {
    if (drawerRef.current) drawerRef.current.open = false;
  }

  return (
    <nav aria-label={navAria}>
      <div className="wrap nav-inner">
        <a className="logo" href="#top">
          <OwlFlatIcon className="nav-owl" />
          ageval<span>.</span>
        </a>
        <div className="nav-links">
          {anchors.map(([href, key]) =>
            key === "docs" ? (
              <Link key={key} href={`/${lang}/docs`}>
                {copy[key]}
              </Link>
            ) : (
              <a key={key} href={`#${href}`}>
                {copy[key]}
              </a>
            ),
          )}
          <a href={`/${otherLang}`}>{copy.lang}</a>
          <details ref={drawerRef} className="nav-drawer">
            <summary className="nav-drawer-btn">{copy.menu}</summary>
            <div className="nav-drawer-panel">
              {anchors.map(([href, key]) =>
                key === "docs" ? (
                  <Link key={key} href={`/${lang}/docs`} onClick={closeDrawer}>
                    {copy[key]}
                  </Link>
                ) : (
                  <a key={key} href={`#${href}`} onClick={closeDrawer}>
                    {copy[key]}
                  </a>
                ),
              )}
              <a href={`/${otherLang}`} onClick={closeDrawer}>
                {copy.lang}
              </a>
            </div>
          </details>
          <a className="btn nav-cta" href={repoUrl} rel="noopener noreferrer">
            {copy.repo}
          </a>
        </div>
      </div>
    </nav>
  );
}
