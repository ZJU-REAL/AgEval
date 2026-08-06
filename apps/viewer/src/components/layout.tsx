import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/components/theme-toggle";

export function Shell({
  children,
  meta,
}: {
  children: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="min-h-full flex flex-col bg-canvas">
      <header className="h-14 border-b border-hairline flex items-center px-6 gap-4 shrink-0">
        <Link to="/" className="font-semibold tracking-tight text-ink text-[15px]">
          BORA
        </Link>
        <span className="text-mute text-sm">viewer</span>
        <div className="flex-1" />
        {meta}
        <ThemeToggle />
      </header>
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-6 py-5">{children}</main>
    </div>
  );
}
