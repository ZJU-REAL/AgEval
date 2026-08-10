import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Shell } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { RegistryHttpError, startWebLogin } from "@/lib/api";

/**
 * Hub login uses browser OAuth (Authorization Code) — same family as Harbor.
 * GitHub redirects back to /login/callback; no device user_code to type.
 * CLI keeps Device Flow via ``bora login``.
 */
export function LoginPage() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const start = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const redirectUri = `${window.location.origin}/login/callback`;
      const { authorize_url } = await startWebLogin(redirectUri);
      // Full navigation — GitHub → back to /login/callback?code=&state=
      window.location.assign(authorize_url);
    } catch (err) {
      setBusy(false);
      if (err instanceof RegistryHttpError) {
        setError(
          err.code === "oauth_not_configured"
            ? `${err.code}: ${err.message}\n→ 配置 BORA_GITHUB_CLIENT_ID / SECRET，并在 GitHub OAuth App 里加 Callback URL：\n  ${window.location.origin}/login/callback`
            : `${err.code}: ${err.message}`,
        );
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, []);

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Datasets", href: "/datasets" },
          { label: "Sign in" },
        ]}
        className="mb-4"
      />
      <h1 className="text-xl font-semibold tracking-tight text-ink mb-2">
        Sign in with GitHub
      </h1>
      <p className="text-sm text-body mb-6 max-w-lg">
        Browser OAuth: you will be sent to GitHub, click{" "}
        <strong>Authorize</strong>, then return here automatically. No device
        code to type (CLI still uses <code className="font-mono">bora login</code>{" "}
        device flow).
      </p>

      <Button type="button" onClick={() => void start()} disabled={busy}>
        {busy ? "Redirecting to GitHub…" : "Sign in with GitHub"}
      </Button>

      {error ? (
        <div className="mt-4 rounded-[8px] border border-error/30 bg-canvas-soft p-3 max-w-lg">
          <p className="text-sm text-error font-medium">Login failed</p>
          <p className="mt-1 text-sm text-error font-mono whitespace-pre-wrap">
            {error}
          </p>
        </div>
      ) : null}

      <p className="mt-8 text-sm text-mute max-w-lg">
        GitHub OAuth App → Authorization callback URL must include:{" "}
        <code className="font-mono text-xs">
          {typeof window !== "undefined"
            ? `${window.location.origin}/login/callback`
            : "http://127.0.0.1:5174/login/callback"}
        </code>
      </p>

      <p className="mt-4 text-sm">
        <Link to="/datasets" className="text-link hover:text-link-deep">
          ← Back to Datasets
        </Link>
      </p>
    </Shell>
  );
}
