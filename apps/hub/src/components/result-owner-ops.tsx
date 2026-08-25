import { Settings, Share2, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog, Modal } from "@/components/ui/confirm-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { toast } from "@/components/ui/toast";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  addResultShare,
  applyRequest,
  deleteResult,
  listResultShares,
  listSuiteRequests,
  removeResultShare,
  setResultVisibility,
  type ResourceRequest,
  type ResultShare,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";

/** Compare Hub appearance specs: optional `role=`, ignore `+digest`. */
function appearanceKey(value: string | undefined): string {
  let text = (value || "").trim();
  if (!text) return "";
  const eq = text.indexOf("=");
  if (eq > 0 && /^[A-Za-z_][A-Za-z0-9_-]*$/.test(text.slice(0, eq).trim())) {
    text = text.slice(eq + 1).trim();
  }
  const plus = text.indexOf("+");
  if (plus >= 0) text = text.slice(0, plus).trim();
  return text.toLowerCase();
}

export function ResultOwnerOps({
  kind,
  resultId,
  visibility,
  complete,
  boundKind,
  boardListed,
  canManage,
  token,
  onVisibility,
  onDeleted,
  onAttached,
}: {
  kind: "attempt" | "suite";
  resultId: string;
  visibility?: string;
  complete?: boolean;
  boundKind?: string;
  boardListed?: boolean;
  canManage: boolean;
  token: string | null;
  onVisibility?: (next: "public" | "private") => void;
  onDeleted?: () => void;
  onAttached?: (suite: Partial<SuiteRow>) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shares, setShares] = useState<ResultShare[]>([]);
  const [requests, setRequests] = useState<ResourceRequest[]>([]);
  const [targetType, setTargetType] = useState<"org" | "user">("org");
  const [targetId, setTargetId] = useState("");
  const [shareOpen, setShareOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [withAttempts, setWithAttempts] = useState(false);
  const [agentRef, setAgentRef] = useState("");

  useEffect(() => {
    if (!shareOpen || !canManage || !token || !resultId) {
      return;
    }
    let cancelled = false;
    setShares([]);
    setRequests([]);
    const shareLoad = listResultShares(kind, resultId, token)
      .then((rows) => {
        if (!cancelled) setShares(rows);
      })
      .catch(() => {
        if (!cancelled) setShares([]);
      });
    const requestLoad =
      kind === "suite"
        ? listSuiteRequests(resultId, token)
            .then((rows) => {
              if (!cancelled) setRequests(rows);
            })
            .catch(() => {
              if (!cancelled) setRequests([]);
            })
        : Promise.resolve();
    void Promise.all([shareLoad, requestLoad]);
    return () => {
      cancelled = true;
    };
  }, [shareOpen, canManage, kind, resultId, token]);

  const pendingAppearance = useMemo(
    () =>
      requests.filter(
        (row) => row.kind === "agent_appearance" && row.status === "pending",
      ),
    [requests],
  );
  const pendingListing = useMemo(
    () =>
      requests.find(
        (row) => row.kind === "leaderboard_list" && row.status === "pending",
      ) ?? null,
    [requests],
  );
  const matchingAppearance = useMemo(
    () => {
      const want = appearanceKey(agentRef);
      if (!want) return undefined;
      return pendingAppearance.find((row) => appearanceKey(row.agent_ref) === want);
    },
    [pendingAppearance, agentRef],
  );

  if (!canManage || !token) return null;
  const authToken = token;

  function fail(err: unknown) {
    if (err instanceof RegistryHttpError) {
      setError(`${err.code}: ${err.message}`);
    } else {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function reloadRequests() {
    if (kind !== "suite") return;
    try {
      setRequests(await listSuiteRequests(resultId, authToken));
    } catch {
      /* keep last */
    }
  }

  async function changeVisibility(next: "public" | "private") {
    if (next === visibility) return;
    setBusy(true);
    setError(null);
    try {
      await setResultVisibility(kind, resultId, next, authToken);
      onVisibility?.(next);
      toast(`Visibility set to ${next}`);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    const id = targetId.trim();
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const row = await addResultShare(
        kind,
        resultId,
        { type: targetType, id },
        authToken,
      );
      setShares((prev) => [...prev, row]);
      setTargetId("");
      toast("Share added");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function unshare(row: ResultShare) {
    setBusy(true);
    setError(null);
    try {
      await removeResultShare(
        kind,
        resultId,
        { type: row.target_type as "org" | "user", id: row.target_id },
        authToken,
      );
      setShares((prev) =>
        prev.filter(
          (s) =>
            !(s.target_type === row.target_type && s.target_id === row.target_id),
        ),
      );
      toast("Share removed");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function requestListing() {
    if (kind !== "suite" || pendingListing) return;
    setBusy(true);
    setError(null);
    try {
      await applyRequest(
        { kind: "leaderboard_list", suite_run_id: resultId },
        authToken,
      );
      await reloadRequests();
      toast("Listing requested");
    } catch (err) {
      if (err instanceof RegistryHttpError && err.code === "conflict") {
        await reloadRequests();
        toast("Listing request already pending");
      } else {
        fail(err);
      }
    } finally {
      setBusy(false);
    }
  }

  async function attachOrRequest() {
    const spec = agentRef.trim();
    if (!spec || kind !== "suite" || matchingAppearance) return;
    setBusy(true);
    setError(null);
    try {
      const row = await applyRequest(
        { kind: "agent_appearance", suite_run_id: resultId, agent: spec },
        authToken,
      );
      if (row.direct_attach || row.attached) {
        onAttached?.(row as Partial<SuiteRow>);
        toast("Agent attached");
        setAgentRef("");
      } else {
        await reloadRequests();
        toast("Appearance requested");
      }
    } catch (err) {
      if (err instanceof RegistryHttpError && err.code === "conflict") {
        await reloadRequests();
        toast("Appearance request already pending");
      } else {
        fail(err);
      }
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await deleteResult(kind, resultId, authToken, {
        withAttempts: kind === "suite" && withAttempts,
      });
      setConfirmDelete(false);
      toast("Result deleted");
      onDeleted?.();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  const current = visibility === "public" ? "public" : "private";

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Job settings"
            aria-haspopup="menu"
            className="h-8 w-8 text-mute"
          >
            <Settings className="h-4 w-4" aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onSelect={() => {
              setError(null);
              setShareOpen(true);
            }}
          >
            <Share2 className="h-3.5 w-3.5" aria-hidden />
            Share
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-error focus:text-error data-[highlighted]:text-error"
            onSelect={() => {
              setError(null);
              setConfirmDelete(true);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Modal
        open={shareOpen}
        title="Share"
        description={
          kind === "suite"
            ? "Who can see this suite, and whether it is listed."
            : "Who can see this attempt."
        }
        error={error}
        onClose={() => {
          if (!busy) {
            setShareOpen(false);
            setError(null);
          }
        }}
      >
        <div className="space-y-4">
          <div className="space-y-2">
            <p className="text-xs font-medium text-mute uppercase tracking-wide">
              Visibility
            </p>
            <Select
              value={current}
              onValueChange={(value) => {
                if (value === "public" || value === "private") {
                  void changeVisibility(value);
                }
              }}
              disabled={busy}
            >
              <SelectTrigger
                aria-label="Result visibility"
                className="h-8 min-w-0 w-auto font-mono text-xs"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="public">public</SelectItem>
                <SelectItem value="private">private</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {kind === "suite" ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-mute uppercase tracking-wide">
                Attach published agent
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  value={agentRef}
                  onChange={(e) => setAgentRef(e.target.value)}
                  placeholder="org/name@version"
                  className="h-8 min-w-0 flex-1 font-mono text-xs"
                  disabled={busy}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void attachOrRequest();
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy || !agentRef.trim() || Boolean(matchingAppearance)}
                  onClick={() => void attachOrRequest()}
                >
                  {matchingAppearance ? "Pending" : "Attach"}
                </Button>
              </div>
              {matchingAppearance ? (
                <p className="text-xs text-body">
                  Appearance request pending for{" "}
                  <span className="font-mono">{matchingAppearance.agent_ref}</span>
                  . Waiting on the agent org owner.
                </p>
              ) : pendingAppearance.length > 0 ? (
                <ul className="space-y-1 text-xs text-body">
                  {pendingAppearance.map((row) => (
                    <li key={row.request_id}>
                      Pending:{" "}
                      <span className="font-mono">
                        {row.agent_ref || "agent"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {kind === "suite" &&
          ((complete && boundKind === "release" && !boardListed) ||
            pendingListing) ? (
            <div className="space-y-2">
              <p className="text-xs font-medium text-mute uppercase tracking-wide">
                Public board
              </p>
              {pendingListing ? (
                <p className="text-xs text-pretty break-words text-body">
                  Listing request pending. Waiting on the dataset org owner.
                </p>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy}
                  onClick={() => void requestListing()}
                >
                  Request listing
                </Button>
              )}
            </div>
          ) : null}

          <div className="space-y-2">
            <p className="text-xs font-medium text-mute uppercase tracking-wide">
              Share with
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={targetType}
                onValueChange={(value) => {
                  if (value === "org" || value === "user") setTargetType(value);
                }}
                disabled={busy}
              >
                <SelectTrigger className="h-8 min-w-0 w-auto font-mono text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="org">org</SelectItem>
                  <SelectItem value="user">user</SelectItem>
                </SelectContent>
              </Select>
              <Input
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                placeholder={targetType === "org" ? "org-id" : "github-login"}
                className="h-8 min-w-0 flex-1 font-mono text-xs"
                disabled={busy}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void share();
                }}
              />
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy || !targetId.trim()}
                onClick={() => void share()}
              >
                Share
              </Button>
            </div>
            {shares.length === 0 ? (
              <p className="text-xs text-mute">Not shared with anyone yet.</p>
            ) : (
              <ul className="divide-y divide-hairline rounded-[6px] border border-hairline">
                {shares.map((row) => (
                  <li
                    key={`${row.target_type}:${row.target_id}`}
                    className="flex items-center justify-between gap-2 px-3 py-1.5"
                  >
                    <span className="font-mono text-xs text-body">
                      {row.target_type}/{row.target_id}
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => void unshare(row)}
                    >
                      Revoke
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        open={confirmDelete}
        title={kind === "suite" ? "Delete suite result" : "Delete attempt"}
        description={
          kind === "suite"
            ? "This removes the suite row from the Registry. Linked Attempts stay unless you also delete them below."
            : "This removes this Attempt result and its uploaded evidence from the Registry."
        }
        confirmLabel="Delete"
        busy={busy}
        error={error}
        onCancel={() => {
          if (!busy) {
            setConfirmDelete(false);
            setError(null);
          }
        }}
        onConfirm={() => void remove()}
      >
        {kind === "suite" ? (
          <label className="flex items-center gap-2 text-sm text-body">
            <input
              type="checkbox"
              checked={withAttempts}
              disabled={busy}
              onChange={(e) => setWithAttempts(e.target.checked)}
            />
            Also delete linked Attempts
          </label>
        ) : null}
      </ConfirmDialog>
    </>
  );
}
