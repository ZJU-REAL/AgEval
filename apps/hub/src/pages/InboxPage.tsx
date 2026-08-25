import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";

import { PageHead } from "@/components/page-head";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "@/components/ui/toast";
import {
  decideRequests,
  listInbox,
  type ResourceRequest,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { rememberReturnPath } from "@/lib/return-path";
import { formatDate } from "@/lib/utils";
import { PeekHost, type PeekTarget } from "@/peek-host";

function matchesQuery(row: ResourceRequest, query: string): boolean {
  if (!query) return true;
  const hay = [
    row.kind,
    row.status,
    row.dataset_id,
    row.suite_run_id,
    row.applicant,
    row.agent_ref || "",
    row.owner_org_id,
  ]
    .join(" ")
    .toLowerCase();
  return hay.includes(query);
}

function PeekCell({
  label,
  onPeek,
}: {
  label: string;
  onPeek: () => void;
}) {
  return (
    <button
      type="button"
      className="font-mono text-xs text-link hover:text-link-deep hover:underline underline-offset-2"
      onClick={onPeek}
    >
      {label}
    </button>
  );
}

export function InboxPage() {
  const token = getToken();
  const [rows, setRows] = useState<ResourceRequest[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [peek, setPeek] = useState<PeekTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const closePeek = useCallback(() => setPeek(null), []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    listInbox(token)
      .then((items) => {
        if (cancelled) return;
        setRows(items);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const needle = query.trim().toLowerCase();
  const pending = useMemo(
    () =>
      rows.filter((row) => row.status === "pending").filter((row) => matchesQuery(row, needle)),
    [rows, needle],
  );
  const history = useMemo(
    () =>
      rows
        .filter((row) => row.status !== "pending")
        .filter((row) => matchesQuery(row, needle))
        .sort((a, b) => (b.decided_at || b.created_at || 0) - (a.decided_at || a.created_at || 0)),
    [rows, needle],
  );
  const pendingIds = useMemo(() => pending.map((r) => r.request_id), [pending]);

  if (!token) {
    rememberReturnPath("/inbox");
    return <Navigate to="/login" replace />;
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function peekDataset(row: ResourceRequest) {
    setPeek({ type: "dataset", datasetId: row.dataset_id });
  }

  function peekSuite(row: ResourceRequest) {
    setPeek({
      type: "dataset",
      datasetId: row.dataset_id,
      search: `tab=leaderboard&suite=${encodeURIComponent(row.suite_run_id)}`,
    });
  }

  function peekApplicant(row: ResourceRequest) {
    setPeek({ type: "user", login: row.applicant });
  }

  async function decide(action: "approve" | "reject") {
    const ids = pendingIds.filter((id) => selected.has(id));
    if (!ids.length) return;
    setBusy(true);
    setError(null);
    try {
      const payload = await decideRequests(ids, action, token);
      const returned = payload.items || [];
      setRows((prev) => {
        const byId = new Map(returned.map((item) => [item.request_id, item]));
        return prev.map((row) => byId.get(row.request_id) || row);
      });
      setSelected(new Set());
      toast(action === "approve" ? "Requests approved" : "Requests rejected");
    } catch (err) {
      if (err instanceof RegistryHttpError) {
        setError(`${err.code}: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHead
        title="Inbox"
        sub="Pending listing and appearance requests you can decide."
      />
      {error ? <p className="text-sm font-mono text-error">{error}</p> : null}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search requests"
          aria-label="Search requests"
          className="h-8 min-w-0 flex-1 basis-56"
        />
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            disabled={busy || pendingIds.every((id) => !selected.has(id))}
            onClick={() => void decide("approve")}
          >
            Approve
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || pendingIds.every((id) => !selected.has(id))}
            onClick={() => void decide("reject")}
          >
            Reject
          </Button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : pending.length === 0 ? (
        <p className="text-sm text-mute">No pending requests.</p>
      ) : (
        <div className="overflow-hidden rounded-[8px] border border-hairline">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <input
                    type="checkbox"
                    aria-label="Select all pending"
                    checked={
                      pendingIds.length > 0 &&
                      pendingIds.every((id) => selected.has(id))
                    }
                    onChange={() => {
                      setSelected((prev) =>
                        prev.size === pendingIds.length ? new Set() : new Set(pendingIds),
                      );
                    }}
                  />
                </TableHead>
                <TableHead>Kind</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>Suite</TableHead>
                <TableHead>Applicant</TableHead>
                <TableHead>Agent</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pending.map((row) => (
                <TableRow key={row.request_id}>
                  <TableCell>
                    <input
                      type="checkbox"
                      aria-label={`Select ${row.request_id}`}
                      checked={selected.has(row.request_id)}
                      onChange={() => toggle(row.request_id)}
                    />
                  </TableCell>
                  <TableCell className="text-xs text-body">{row.kind}</TableCell>
                  <TableCell>
                    <PeekCell label={row.dataset_id} onPeek={() => peekDataset(row)} />
                  </TableCell>
                  <TableCell>
                    <PeekCell label={row.suite_run_id} onPeek={() => peekSuite(row)} />
                  </TableCell>
                  <TableCell>
                    <PeekCell label={row.applicant} onPeek={() => peekApplicant(row)} />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {row.agent_ref || "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {history.length > 0 ? (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-ink">History</h2>
          <div className="overflow-hidden rounded-[8px] border border-hairline">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Dataset</TableHead>
                  <TableHead>Suite</TableHead>
                  <TableHead>Applicant</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Decided</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((row) => (
                  <TableRow key={row.request_id}>
                    <TableCell className="text-xs text-body">{row.status}</TableCell>
                    <TableCell className="text-xs text-body">{row.kind}</TableCell>
                    <TableCell>
                      <PeekCell label={row.dataset_id} onPeek={() => peekDataset(row)} />
                    </TableCell>
                    <TableCell>
                      <PeekCell label={row.suite_run_id} onPeek={() => peekSuite(row)} />
                    </TableCell>
                    <TableCell>
                      <PeekCell label={row.applicant} onPeek={() => peekApplicant(row)} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {row.agent_ref || "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-mute">
                      {formatDate(row.decided_at ?? row.created_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      ) : null}

      {peek ? <PeekHost peek={peek} onClose={closePeek} /> : null}
    </div>
  );
}
