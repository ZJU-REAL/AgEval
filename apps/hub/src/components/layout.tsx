import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { clearToken, getGithubUser, getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "text-sm transition-colors px-1 py-0.5",
    isActive ? "text-ink font-medium" : "text-body hover:text-ink",
  );
}

export function Shell({
  children,
  meta,
}: {
  children: ReactNode;
  meta?: ReactNode;
}) {
  const token = getToken();
  const githubUser = getGithubUser();

  return (
    <div className="min-h-full flex flex-col bg-canvas">
      <header className="h-14 border-b border-hairline flex items-center px-6 gap-4 shrink-0">
        <Link to="/datasets" className="font-semibold tracking-tight text-ink text-[15px]">
          BORA
        </Link>
        <span className="text-mute text-sm">hub</span>
        <nav className="flex items-center gap-4 text-sm ml-2">
          <NavLink to="/datasets" className={navClass} end={false}>
            Datasets
          </NavLink>
          <NavLink to="/organizations" className={navClass}>
            Organizations
          </NavLink>
        </nav>
        <div className="flex-1" />
        {meta}
        {token ? (
          <>
            {githubUser ? (
              <span className="text-xs text-mute font-mono hidden sm:inline">
                @{githubUser}
              </span>
            ) : null}
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
          </>
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
