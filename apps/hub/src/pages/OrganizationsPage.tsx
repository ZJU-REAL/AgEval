import { Building2, Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { HoverTip } from "@/components/hover-tip";
import { OfficialMark } from "@/components/official-mark";
import { PageHead } from "@/components/page-head";
import { SignInLink } from "@/components/sign-in-button";
import { Button } from "@/components/ui/button";
import { FloatingField } from "@/components/ui/floating-field";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createOrg,
  joinOrgWithInvite,
  listOrgs,
  latestPackageByDataset,
  listPackages,
  type OrgRow,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

export function OrganizationsPage() {
  const navigate = useNavigate();
  const token = getToken();
  const [orgs, setOrgs] = useState<OrgRow[]>([]);
  const [datasets, setDatasets] = useState<PackageRelease[]>([]);
  const [plugins, setPlugins] = useState<PackageRelease[]>([]);
  const [agents, setAgents] = useState<PackageRelease[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const [joinOpen, setJoinOpen] = useState(false);
  const [inviteKey, setInviteKey] = useState("");
  const [joinBusy, setJoinBusy] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [orgDisplayName, setOrgDisplayName] = useState("");
  const [orgDescription, setOrgDescription] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const orgNameOk = /^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$/.test(
    orgName.trim().toLowerCase(),
  );

  function reload() {
    if (!token) return;
    setLoading(true);
    Promise.all([
      listOrgs(token),
      listPackages(token, { packageKind: "dataset" }),
      listPackages(token, { packageKind: "plugin" }),
      listPackages(token, { packageKind: "agent" }),
    ])
      .then(([orgRows, datasetRows, pluginRows, agentRows]) => {
        setOrgs(orgRows);
        setDatasets(datasetRows);
        setPlugins(pluginRows);
        setAgents(agentRows);
        setError(null);
      })
      .catch((err: unknown) => {
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setOrgs([]);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setOrgs([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all([
      listOrgs(token),
      listPackages(token, { packageKind: "dataset" }),
      listPackages(token, { packageKind: "plugin" }),
      listPackages(token, { packageKind: "agent" }),
    ])
      .then(([orgRows, datasetRows, pluginRows, agentRows]) => {
        if (cancelled) return;
        setOrgs(orgRows);
        setDatasets(datasetRows);
        setPlugins(pluginRows);
        setAgents(agentRows);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setOrgs([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const datasetCountByOrg = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of latestPackageByDataset(datasets)) {
      if (!row.org_id) continue;
      counts.set(row.org_id, (counts.get(row.org_id) ?? 0) + 1);
    }
    return counts;
  }, [datasets]);

  const pluginCountByOrg = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of latestPackageByDataset(plugins)) {
      if (!row.org_id) continue;
      counts.set(row.org_id, (counts.get(row.org_id) ?? 0) + 1);
    }
    return counts;
  }, [plugins]);

  const agentCountByOrg = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of latestPackageByDataset(agents)) {
      if (!row.org_id) continue;
      counts.set(row.org_id, (counts.get(row.org_id) ?? 0) + 1);
    }
    return counts;
  }, [agents]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return orgs;
    return orgs.filter(
      (o) =>
        o.org_id.toLowerCase().includes(q) ||
        (o.display_name || "").toLowerCase().includes(q) ||
        (o.name || "").toLowerCase().includes(q),
    );
  }, [orgs, query]);

  async function submitCreate() {
    if (!token) return;
    const name = orgName.trim().toLowerCase();
    if (!/^[a-z0-9]([a-z0-9_-]{0,62}[a-z0-9])?$/.test(name)) {
      setCreateError("Slug must be lowercase [a-z0-9][a-z0-9_-]*");
      return;
    }
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createOrg(
        {
          name,
          display_name: orgDisplayName.trim() || name,
          description: orgDescription.trim(),
        },
        token,
      );
      setCreateOpen(false);
      setOrgName("");
      setOrgDisplayName("");
      setOrgDescription("");
      navigate(`/organizations/${encodeURIComponent(created.org_id || name)}`);
    } catch (err: unknown) {
      if (err instanceof RegistryHttpError) {
        setCreateError(`${err.code}: ${err.message}`);
      } else {
        setCreateError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setCreateBusy(false);
    }
  }

  async function submitJoin() {
    if (!token) return;
    const key = inviteKey.trim();
    if (!key) {
      setJoinError("Invite key is required");
      return;
    }
    setJoinBusy(true);
    setJoinError(null);
    try {
      const joined = await joinOrgWithInvite(key, token);
      setJoinOpen(false);
      setInviteKey("");
      reload();
      if (joined.org_id) {
        navigate(`/organizations/${encodeURIComponent(joined.org_id)}`);
      }
    } catch (err: unknown) {
      if (err instanceof RegistryHttpError) {
        setJoinError(`${err.code}: ${err.message}`);
      } else {
        setJoinError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setJoinBusy(false);
    }
  }

  return (
    <>
      <PageHead
        title="Organizations"
        sub="Organizations you belong to. Packages are published under an org."
      />

      {!token ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-body">
          <p className="font-medium text-ink">Sign in required</p>
          <p className="mt-1 text-mute">
            <SignInLink /> to list your organizations.
          </p>
        </div>
      ) : loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load organizations</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : (
        <>
          <div className="mb-3 flex w-full items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your organizations…"
              aria-label="Search organizations"
              className="flex-1 min-w-0 focus-visible:border-hairline"
            />
            <HoverTip content="Join with invite key">
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="shrink-0"
              aria-label="Join organization with invite key"
              onClick={() => {
                setJoinOpen(true);
                setJoinError(null);
              }}
            >
              <Plus className="h-4 w-4" />
            </Button>
            </HoverTip>
            <Button
              type="button"
              size="sm"
              className="shrink-0"
              onClick={() => {
                setCreateOpen(true);
                setCreateError(null);
              }}
            >
              New org
            </Button>
          </div>
          {filtered.length === 0 ? (
            <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm">
              <div className="flex justify-center mb-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
                  <Building2 className="h-8 w-8" strokeWidth={1.5} aria-hidden />
                </div>
              </div>
              <p className="font-medium text-ink">No organizations</p>
              <p className="mt-1 text-mute">
                Create one here, or join with an invite key.
              </p>
              <div className="mt-4 flex justify-center">
                <Button
                  type="button"
                  onClick={() => {
                    setCreateOpen(true);
                    setCreateError(null);
                  }}
                >
                  Create organization
                </Button>
              </div>
            </div>
          ) : (
            <div className="rounded-[8px] border border-hairline overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Organization</TableHead>
                    <TableHead>ID</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead className="text-right tabular-nums">
                      Datasets
                    </TableHead>
                    <TableHead className="text-right tabular-nums">
                      Plugins
                    </TableHead>
                    <TableHead className="text-right tabular-nums">
                      Agents
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((org) => (
                    <TableRow
                      key={org.org_id}
                      className="cursor-pointer"
                      onClick={() =>
                        navigate(
                          `/organizations/${encodeURIComponent(org.org_id)}`,
                        )
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(
                            `/organizations/${encodeURIComponent(org.org_id)}`,
                          );
                        }
                      }}
                      tabIndex={0}
                      role="link"
                    >
                      <TableCell className="font-medium text-ink">
                        <span className="inline-flex items-center gap-1.5 min-w-0">
                          <span className="truncate">
                            {org.display_name || org.name || org.org_id}
                          </span>
                          {org.official ? <OfficialMark kind="org" /> : null}
                        </span>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-mute">
                        @{org.org_id}
                      </TableCell>
                      <TableCell className="text-body capitalize text-sm">
                        {org.role || "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-body">
                        {datasetCountByOrg.get(org.org_id) ?? 0}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-body">
                        {pluginCountByOrg.get(org.org_id) ?? 0}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-body">
                        {agentCountByOrg.get(org.org_id) ?? 0}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          <p className="text-xs text-mute mt-3 tabular-nums">
            {filtered.length} organization
            {filtered.length === 1 ? "" : "s"}
          </p>
        </>
      )}

      {createOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-org-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !createBusy) setCreateOpen(false);
          }}
        >
          <div className="w-full max-w-md rounded-[12px] border border-hairline bg-canvas shadow-[var(--viewer-shadow-pop)] p-5 space-y-4">
            <div>
              <h2
                id="create-org-title"
                className="text-lg font-semibold tracking-tight text-ink"
              >
                Create organization
              </h2>
              <p className="text-sm text-mute mt-1">
                You become the owner. Packages publish under this slug.
              </p>
            </div>
            <div>
              <label
                htmlFor="org-name-input"
                className="text-xs font-medium text-mute uppercase tracking-wide"
              >
                Slug
              </label>
              <Input
                id="org-name-input"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="my-lab"
                className="mt-1.5 font-mono text-sm"
                autoFocus
                disabled={createBusy}
                maxLength={64}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitCreate();
                }}
              />
              <p className="mt-1 text-xs text-mute">
                Lowercase letters, digits, hyphen, underscore.
              </p>
            </div>
            <div>
              <label
                htmlFor="org-display-input"
                className="text-xs font-medium text-mute uppercase tracking-wide"
              >
                Display name
              </label>
              <Input
                id="org-display-input"
                value={orgDisplayName}
                onChange={(e) => setOrgDisplayName(e.target.value)}
                placeholder="Optional — defaults to the slug"
                className="mt-1.5 text-sm"
                disabled={createBusy}
                maxLength={80}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitCreate();
                }}
              />
            </div>
            <FloatingField
              multiline
              id="org-description-input"
              label="Description"
              value={orgDescription}
              onChange={(e) => setOrgDescription(e.target.value)}
              disabled={createBusy}
              maxLength={500}
            />
            {createError ? (
              <p className="text-sm text-error font-mono">{createError}</p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={createBusy}
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={createBusy || !orgNameOk}
                onClick={() => void submitCreate()}
              >
                {createBusy ? "Creating…" : "Create"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {joinOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="join-org-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !joinBusy) setJoinOpen(false);
          }}
        >
          <div className="w-full max-w-md rounded-[12px] border border-hairline bg-canvas shadow-[var(--viewer-shadow-pop)] p-5 space-y-4">
            <div>
              <h2
                id="join-org-title"
                className="text-lg font-semibold tracking-tight text-ink"
              >
                Join organization
              </h2>
              <p className="text-sm text-mute mt-1">
                Paste an invite key from an org owner. You will join as a member.
              </p>
            </div>
            <div>
              <label
                htmlFor="invite-key-input"
                className="text-xs font-medium text-mute uppercase tracking-wide"
              >
                Invite key
              </label>
              <Input
                id="invite-key-input"
                value={inviteKey}
                onChange={(e) => setInviteKey(e.target.value)}
                placeholder="ageval-inv_…"
                className="mt-1.5 font-mono text-sm"
                autoFocus
                disabled={joinBusy}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void submitJoin();
                }}
              />
            </div>
            {joinError ? (
              <p className="text-sm text-error font-mono">{joinError}</p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={joinBusy}
                onClick={() => setJoinOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={joinBusy || !inviteKey.trim()}
                onClick={() => void submitJoin()}
              >
                {joinBusy ? "Joining…" : "Join"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
