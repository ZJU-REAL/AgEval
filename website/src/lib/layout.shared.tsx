import { createElement } from "react";
import Image from "next/image";
import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import { appName, gitConfig } from "./shared";
import { i18n, type SiteLocale } from "./i18n";
import { uiTranslations } from "fumadocs-ui/i18n";
import { zhCN } from "@fumadocs/language/zh-cn";

export const translations = i18n
  .translations()
  .extend(uiTranslations())
  .preset("zh-CN", zhCN())
  .add({
    en: { displayName: "English" },
    "zh-CN": { displayName: "简体中文" },
  });

export function baseOptions(locale: SiteLocale): BaseLayoutProps {
  return {
    nav: {
      title: createElement(Image, {
        className: "bora-nav-logo",
        src: "/images/bora-hero.png",
        alt: appName,
        width: 60,
        height: 40,
        unoptimized: true,
      }),
      url: `/${locale}`,
    },
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
  };
}
