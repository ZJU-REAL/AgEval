import { useSyncExternalStore } from "react";

/** Apple keyboard uses meta (⌘); Windows / Linux use Control. */
export type ModKey = "meta" | "ctrl";

export function isAppleNavigator(
  nav: Pick<Navigator, "platform" | "userAgent"> & {
    userAgentData?: { platform?: string };
  },
): boolean {
  const platform = nav.userAgentData?.platform || nav.platform || "";
  if (/mac|iphone|ipad|ipod/i.test(platform)) return true;
  return /mac|iphone|ipad|ipod/i.test(nav.userAgent || "");
}

function readModKey(): ModKey {
  if (typeof navigator === "undefined") return "ctrl";
  return isAppleNavigator(navigator) ? "meta" : "ctrl";
}

const emptySubscribe = () => () => {};

export function useModKey(): ModKey {
  return useSyncExternalStore(emptySubscribe, readModKey, () => "ctrl");
}

export function modKeyShortcut(mod: ModKey, key: string): string {
  const letter = key.trim().toUpperCase();
  return mod === "meta" ? `Meta+${letter}` : `Control+${letter}`;
}
