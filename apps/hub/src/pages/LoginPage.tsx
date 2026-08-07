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
  const [deviceCodeValue, setDeviceCodeValue] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("idle");
  const intervalRef = useRef<number | null>(null);

  const stopPoll = useCallback(() => {
    if (intervalRef.current != null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setStatus("requesting");
    stopPoll();
    try {
      const code = await deviceCode();
      setUserCode(code.user_code);
      setVerifyUri(code.verification_uri_complete || code.verification_uri);
      setDeviceCodeValue(code.device_code);
      setStatus("pending");
      const intervalMs = Math.max(2, code.interval ?? 5) * 1000;
      intervalRef.current = window.setInterval(async () => {
        try {
          const poll = await devicePoll(code.device_code);
          if (poll.status === "authorization_pending") return;
          const token = poll.access_token || poll.token;
          if (token) {
            setToken(token);
            stopPoll();
            setStatus("done");
            navigate("/datasets");
          }
        } catch (err) {
          if (err instanceof RegistryHttpError && err.status === 202) return;
          // keep polling on soft errors
        }
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
      <p className="text-sm text-body max-w-xl mb-6">
        Device login uses the same Registry OAuth flow as{" "}
        <code className="font-mono">bora login</code>. The token stays in this
        browser only (localStorage) — never in packages or evidence.
      </p>

      {status === "idle" || status === "error" ? (
        <Button type="button" onClick={() => void start()}>
          Start device login
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
          <p className="text-xs text-mute">
            Waiting for authorization…{deviceCodeValue ? "" : ""}
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="mt-4 text-sm text-error font-mono">{error}</p>
      ) : null}

      <p className="mt-8 text-sm">
        <Link to="/datasets" className="text-link hover:text-link-deep">
          ← Back to Datasets
        </Link>
      </p>
    </Shell>
  );
}
