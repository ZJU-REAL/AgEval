import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Shell } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { deviceCode, devicePoll, RegistryHttpError } from "@/lib/api";
import { setToken } from "@/lib/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const [userCode, setUserCode] = useState<string | null>(null);
  const [verifyUri, setVerifyUri] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const [pollHint, setPollHint] = useState<string>("Waiting for authorization…");
  const intervalRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const stoppedRef = useRef(false);

  const stopPoll = useCallback(() => {
    stoppedRef.current = true;
    if (intervalRef.current != null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setStatus("requesting");
    setPollHint("Waiting for authorization…");
    stopPoll();
    stoppedRef.current = false;
    try {
      const code = await deviceCode();
      setUserCode(code.user_code);
      setVerifyUri(
        code.verification_uri_complete ||
          code.verification_uri ||
          "https://github.com/login/device",
      );
      setStatus("pending");

      const intervalMs = Math.max(5, code.interval ?? 5) * 1000;

      const tick = async () => {
        if (stoppedRef.current || inFlightRef.current) return;
        inFlightRef.current = true;
        try {
          const poll = await devicePoll(code.device_code);
          if (stoppedRef.current) return;
          if (poll.status === "authorization_pending") {
            setPollHint("Waiting for authorization…");
            return;
          }
          const token = poll.token || poll.access_token;
          if (token) {
            setToken(token);
            stopPoll();
            setStatus("done");
            setPollHint(
              poll.github_user
                ? `Signed in as ${poll.github_user}`
                : "Signed in",
            );
            navigate("/datasets");
            return;
          }
          // Unexpected 200 shape
          setPollHint("Unexpected poll response (no token); retrying…");
        } catch (err) {
          if (stoppedRef.current) return;
          // Terminal failures: stop and surface (allowlist, expired, denied).
          if (err instanceof RegistryHttpError) {
            if (err.status === 202) {
              setPollHint("Waiting for authorization…");
              return;
            }
            stopPoll();
            setStatus("error");
            setError(`${err.code}: ${err.message}`);
            return;
          }
          // Network blip — keep polling, show soft hint
          setPollHint(
            err instanceof Error
              ? `Poll error: ${err.message} (retrying…)`
              : "Poll error (retrying…)",
          );
        } finally {
          inFlightRef.current = false;
        }
      };

      // Poll immediately, then on interval (do not wait first full interval).
      void tick();
      intervalRef.current = window.setInterval(() => {
        void tick();
      }, intervalMs);
    } catch (err) {
      setStatus("error");
      if (err instanceof RegistryHttpError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, [navigate, stopPoll]);

  useEffect(() => () => stopPoll(), [stopPoll]);

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
      <p className="text-sm text-body mb-6 whitespace-nowrap">
        Device login uses the same Registry OAuth flow as{" "}
        <code className="font-mono">bora login</code>. The token stays in this
        browser only (localStorage) — never in packages or evidence.
      </p>

      {status === "idle" || status === "error" ? (
        <Button type="button" onClick={() => void start()}>
          {status === "error" ? "Try again" : "Start device login"}
        </Button>
      ) : null}

      {status === "requesting" ? (
        <p className="text-sm text-mute">Requesting device code…</p>
      ) : null}

      {status === "pending" && userCode ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 space-y-3 max-w-lg">
          <p className="text-sm text-body">
            Open the verification URL and enter this code:
          </p>
          <p className="font-mono text-2xl tracking-widest text-ink">{userCode}</p>
          {verifyUri ? (
            <a
              href={verifyUri}
              target="_blank"
              rel="noreferrer"
              className="text-link hover:text-link-deep text-sm break-all"
            >
              {verifyUri}
            </a>
          ) : null}
          <p className="text-xs text-mute">{pollHint}</p>
        </div>
      ) : null}

      {status === "done" ? (
        <p className="text-sm text-body">{pollHint}</p>
      ) : null}

      {error ? (
        <p className="mt-4 text-sm text-error font-mono whitespace-pre-wrap">
          {error}
        </p>
      ) : null}

      <p className="mt-8 text-sm">
        <Link to="/datasets" className="text-link hover:text-link-deep">
          ← Back to Datasets
        </Link>
      </p>
    </Shell>
  );
}
