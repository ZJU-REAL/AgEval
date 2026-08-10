import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Shell } from "@/components/layout";
import { completeWebLogin, RegistryHttpError } from "@/lib/api";
import { setToken } from "@/lib/auth";

/** OAuth redirect target: ?code=&state= → Registry token → /datasets */
export function LoginCallbackPage() {
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  // React StrictMode remounts effects in dev; exchange GitHub code exactly once.
  const startedRef = useRef(false);

  const code = params.get("code");
  const oauthState = params.get("state");
  const oauthError = params.get("error");
  const desc = params.get("error_description");

  useEffect(() => {
    if (oauthError) {
      setError(`${oauthError}: ${desc || "GitHub denied authorization"}`);
      return;
    }
    if (!code || !oauthState) {
      setError("Missing code/state in callback URL. Start sign-in again.");
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    const redirectUri = `${window.location.origin}/login/callback`;
    completeWebLogin({ code, state: oauthState, redirectUri })
      .then((session) => {
        setToken(
          session.token,
          session.github_user,
          session.github_name,
          session.avatar_url,
        );
        window.location.replace("/datasets");
      })
      .catch((err: unknown) => {
        if (err instanceof RegistryHttpError) {
          setError(
            err.code === "login_not_allowed"
              ? `${err.code}: ${err.message}\n→ 把你的 GitHub login 加入 BORA_GITHUB_LOGIN_ALLOWLIST 并重启 Registry。`
              : err.code === "invalid_state"
                ? `${err.code}: ${err.message}\n→ 开发模式勿重复打开 callback；请从 /login 重新 Sign in（不要刷新本页）。`
                : `${err.code}: ${err.message}`,
          );
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      });
  }, [code, oauthState, oauthError, desc]);

  return (
    <Shell>
      <h1 className="text-xl font-semibold tracking-tight text-ink mb-2">
        Completing sign-in…
      </h1>
      {error ? (
        <div className="mt-4 rounded-[8px] border border-error/30 bg-canvas-soft p-3 max-w-lg">
          <p className="text-sm text-error font-medium">Login failed</p>
          <p className="mt-1 text-sm text-error font-mono whitespace-pre-wrap">
            {error}
          </p>
          <p className="mt-3 text-sm">
            <Link to="/login" className="text-link hover:text-link-deep">
              ← Try again
            </Link>
          </p>
        </div>
      ) : (
        <p className="text-sm text-mute">
          Exchanging GitHub code for a Registry token…
        </p>
      )}
    </Shell>
  );
}
