import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { SignInButton } from "@/components/sign-in-button";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  clearToken,
  getGithubAvatar,
  getGithubName,
  getGithubUser,
  getToken,
} from "@/lib/auth";
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
  const githubName = getGithubName();
  const githubAvatar = getGithubAvatar();
  const displayName = githubName || githubUser;

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
            {displayName ? (
              <span className="hidden sm:inline-flex items-center gap-2 min-w-0 max-w-[14rem]">
                {githubAvatar || githubUser ? (
                  <img
                    src={
                      githubAvatar ||
                      `https://github.com/${encodeURIComponent(githubUser || "")}.png?size=64`
                    }
                    alt=""
                    width={28}
                    height={28}
                    className="h-7 w-7 rounded-full border border-hairline bg-canvas-soft object-cover shrink-0"
                  />
                ) : null}
                <span className="text-sm text-body truncate" title={githubUser || undefined}>
                  {displayName}
                </span>
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
          <SignInButton />
        )}
        <ThemeToggle />
      </header>
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-6 py-5">{children}</main>
    </div>
  );
}
