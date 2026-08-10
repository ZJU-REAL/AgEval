import { useEffect } from "react";

/**
 * Deep-link entry only: immediately start GitHub OAuth (no intermediate UI).
 * Prefer header / in-page SignInButton so users never land here.
 */
export function LoginPage() {
  useEffect(() => {
    // Full navigation — do not render a Hub form first.
    void import("@/lib/github-login").then(({ redirectToGitHubLogin }) =>
      redirectToGitHubLogin().catch(() => {
        // Hard fail: stay blank; user can use header Sign in.
      }),
    );
  }, []);

  return null;
}
