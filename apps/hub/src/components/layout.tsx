import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { clearToken, getToken } from "@/lib/auth";

export function Shell({
  children,
  meta,
}: {
  children: ReactNode;
  meta?: ReactNode;
}) {
  const token = getToken();

  return (
    <div className="min-h-full flex flex-col bg-canvas">
      <header className="h-14 border-b border-hairline flex items-center px-6 gap-4 shrink-0">
        <Link to="/datasets" className="font-semibold tracking-tight text-ink text-[15px]">
          BORA
        </Link>
        <span className="text-mute text-sm">hub</span>
        <nav className="flex items-center gap-3 text-sm">
          <Link to="/datasets" className="text-body hover:text-ink transition-colors">
            Datasets
          </Link>
        </nav>
        <div className="flex-1" />
        {meta}
        {token ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              clearToken();
              window.location.reload();
            }}
          >
            Sign out
          </Button>
        ) : (
          <Button asChild variant="outline" size="sm">
            <Link to="/login">Sign in</Link>
          </Button>
        )}
        <ThemeToggle />
      </header>
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-6 py-5">{children}</main>
    </div>
  );
}
