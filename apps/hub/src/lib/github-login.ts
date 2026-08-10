import { RegistryHttpError, startWebLogin } from "@/lib/api";

/** Start Hub browser OAuth and navigate to GitHub (full page). */
export async function redirectToGitHubLogin(): Promise<void> {
  const redirectUri = `${window.location.origin}/login/callback`;
  const { authorize_url } = await startWebLogin(redirectUri);
  window.location.assign(authorize_url);
}

export function formatLoginError(err: unknown): string {
  if (err instanceof RegistryHttpError) {
    if (err.code === "oauth_not_configured") {
      return "GitHub OAuth is not configured on the Registry.";
    }
    if (err.code === "login_not_allowed") {
      return "Your GitHub account is not on the allowlist.";
    }
    return err.message || err.code;
  }
  return err instanceof Error ? err.message : String(err);
}
