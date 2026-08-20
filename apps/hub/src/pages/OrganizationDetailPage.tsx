import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Plus } from "lucide-react";

import { CatalogHead } from "@/components/page-head";
import { DisplayNameEditor } from "@/components/display-name-editor";
import { HoverTip } from "@/components/hover-tip";
import { OfficialMark } from "@/components/official-mark";
import { SignInLink } from "@/components/sign-in-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  addOrgMember,
  createOrgInviteKey,
  dissolveOrg,
  encodeDatasetId,
  getOrg,
  packageDisplayTitle,
  leaveOrg,
  listOrgInviteKeys,
  listOrgMembers,
  latestPackageByDataset,
  updateOrgDisplayName,
  listPackages,
  listResultShares,
  listSuites,
  removeOrgMember,
  revokeOrgInviteKey,
  setOrgMemberRole,
  transferOrg,
  type OrgInviteKey,
  type OrgMember,
  type OrgRow,
  type PackageRelease,
  type SuiteRow,
  RegistryHttpError,
} from "@/lib/api";
import { getGithubUser, getToken } from "@/lib/auth";
import { cn, formatDate } from "@/lib/utils";

type Tab = "overview" | "settings";

/** Active keys only — revoked rows are dropped from the UI list. */
function activeInviteKeys(keys: OrgInviteKey[]): OrgInviteKey[] {
  return keys.filter((k) => !k.revoked_at);
}

export function OrganizationDetailPage() {
  const { orgId: rawOrgId } = useParams();
  const orgId = rawOrgId ? decodeURIComponent(rawOrgId) : "";
  const navigate = useNavigate();
  const token = getToken();
  const [tab, setTab] = useState<Tab>("overview");
  const [org, setOrg] = useState<OrgRow | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [datasets, setDatasets] = useState<PackageRelease[]>([]);
  const [plugins, setPlugins] = useState<PackageRelease[]>([]);
  const [sharedSuites, setSharedSuites] = useState<SuiteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [inviteKeys, setInviteKeys] = useState<OrgInviteKey[]>([]);
  const [inviteLoadError, setInviteLoadError] = useState<string | null>(null);
  const [maxUses, setMaxUses] = useState("");
  const [expiresDays, setExpiresDays] = useState("7");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  /** Full key shown once after create (never re-fetched from list). */
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [revealCopied, setRevealCopied] = useState(false);
  /** First click arms delete; second confirms. */
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [revokeBusy, setRevokeBusy] = useState<string | null>(null);

  const [dangerConfirm, setDangerConfirm] = useState(false);
  const [dangerBusy, setDangerBusy] = useState(false);
  const [dangerError, setDangerError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [addLogin, setAddLogin] = useState("");
  const [addBusy, setAddBusy] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [memberBusy, setMemberBusy] = useState<string | null>(null);
  /** First click arms remove/transfer; second confirms. */
  const [memberConfirm, setMemberConfirm] = useState<string | null>(null);

  const isOwner = (org?.role || "").toLowerCase() === "owner";
  const selfLogin = (getGithubUser() || "").toLowerCase();
  const ownerCount = members.filter((m) => m.role === "owner").length;

  useEffect(() => {
    if (!orgId || !token) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);

    (async () => {
      try {
        const [orgRow, memberRows, datasetRows, pluginRows] = await Promise.all([
          getOrg(orgId, token),
          listOrgMembers(orgId, token),
          listPackages(token, { packageKind: "dataset" }),
          listPackages(token, { packageKind: "plugin" }),
        ]);
        if (cancelled) return;
        setOrg(orgRow);
        setMembers(memberRows);
        const inOrg = (rows: PackageRelease[]) =>
          latestPackageByDataset(rows).filter((p) => p.org_id === orgId);
        setDatasets(inOrg(datasetRows));
        setPlugins(inOrg(pluginRows));
        setError(null);

        // Invite keys: owner-only; ignore 403 for non-owners.
        if ((orgRow.role || "").toLowerCase() === "owner") {
          try {
            const keys = await listOrgInviteKeys(orgId, token);
            if (!cancelled) {
              setInviteKeys(activeInviteKeys(keys));
              setInviteLoadError(null);
            }
          } catch (err: unknown) {
            if (!cancelled) {
              setInviteKeys([]);
              if (err instanceof RegistryHttpError && err.status !== 403) {
                setInviteLoadError(`${err.code}: ${err.message}`);
              }
            }
          }
        } else if (!cancelled) {
          setInviteKeys([]);
        }

        // Shared suite results: visible suites that list this org as a share target.
        try {
          const suites = await listSuites(null, token);
          const candidates = suites.slice(0, 80);
          const hits: SuiteRow[] = [];
          await Promise.all(
            candidates.map(async (s) => {
              if (!s.suite_run_id) return;
              try {
                const shares = await listResultShares(
                  "suite",
                  s.suite_run_id,
                  token,
                );
                const orgKey = orgId.toLowerCase();
                if (
                  shares.some(
                    (sh) =>
                      sh.target_type === "org" &&
                      sh.target_id.toLowerCase() === orgKey,
                  )
                ) {
                  hits.push(s);
                }
              } catch {
                // ignore unreadable share lists
              }
            }),
          );
          if (!cancelled) setSharedSuites(hits);
        } catch {
          if (!cancelled) setSharedSuites([]);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setOrg(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [orgId, token]);

  const title = useMemo(
    () => org?.display_name || org?.name || orgId,
    [org, orgId],
  );

  function memberErr(err: unknown): string {
    if (err instanceof RegistryHttpError) return `${err.code}: ${err.message}`;
    return err instanceof Error ? err.message : String(err);
  }

  async function refreshOrgAndMembers() {
    if (!token) return;
    const [orgRow, memberRows] = await Promise.all([
      getOrg(orgId, token),
      listOrgMembers(orgId, token),
    ]);
    setOrg(orgRow);
    setMembers(memberRows);
  }

  async function confirmMemberAction(
    key: string,
    run: () => Promise<void>,
  ): Promise<void> {
    if (memberConfirm !== key) {
      setMemberConfirm(key);
      setMemberError(null);
      return;
    }
    setMemberBusy(key);
    setMemberError(null);
    try {
      await run();
      setMemberConfirm(null);
    } catch (err: unknown) {
      setMemberError(memberErr(err));
      setMemberConfirm(null);
    } finally {
      setMemberBusy(null);
    }
  }

  async function addMember() {
    if (!token) return;
    const login = addLogin.trim();
    if (!login) return;
    setAddBusy(true);
    setMemberError(null);
    try {
      await addOrgMember(orgId, login, token, "member");
      setAddLogin("");
      setAddOpen(false);
      await refreshOrgAndMembers();
    } catch (err: unknown) {
      setMemberError(memberErr(err));
    } finally {
      setAddBusy(false);
    }
  }

  async function changeRole(userId: string, role: "owner" | "member") {
    if (!token) return;
    setMemberBusy(`role:${userId}`);
    setMemberError(null);
    try {
      await setOrgMemberRole(orgId, userId, role, token);
      await refreshOrgAndMembers();
    } catch (err: unknown) {
      setMemberError(memberErr(err));
    } finally {
      setMemberBusy(null);
    }
  }

  async function removeMember(userId: string) {
    if (!token) return;
    await removeOrgMember(orgId, userId, token);
    await refreshOrgAndMembers();
  }

  async function transferTo(userId: string) {
    if (!token) return;
    await transferOrg(orgId, userId, token);
    await refreshOrgAndMembers();
  }

  if (!token) {
    return (
      <>
        <CatalogHead
          title="Organizations"
          crumbs={[
            { label: "Organizations", href: "/organizations" },
            { label: orgId || "…" },
          ]}
        />
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm">
          <p className="font-medium text-ink">Sign in required</p>
          <p className="mt-1 text-mute">
            <SignInLink /> to view this organization.
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <CatalogHead
        title="Organizations"
        crumbs={[
          { label: "Organizations", href: "/organizations" },
          { label: title },
        ]}
      />

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load organization</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
        </div>
      ) : (
        <>
          <div className="mb-4">
            <DisplayNameEditor
              value={title}
              canEdit={isOwner}
              headingClassName="text-2xl font-semibold tracking-tight text-ink"
              afterTitle={org?.official ? <OfficialMark kind="org" /> : null}
              onSave={async (next) => {
                const updated = await updateOrgDisplayName(orgId, next, token);
                setOrg(updated);
              }}
            />
            <p className="font-mono text-sm text-mute mt-1">@{orgId}</p>
            {org?.role ? (
              <p className="text-xs text-body mt-1 capitalize">
                Your role: {org.role}
              </p>
            ) : null}
          </div>

          <div className="flex gap-1 border-b border-hairline mb-6">
            {(
              [
                ["overview", "Overview"],
                ["settings", "Settings"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={cn(
                  "px-3 py-2 font-mono text-xs uppercase tracking-wide transition-colors border-b-2 -mb-px",
                  tab === id
                    ? "border-link text-ink font-semibold"
                    : "border-transparent text-mute hover:text-body",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "overview" ? (
            <div className="space-y-8">
              <section>
                <h2 className="text-sm font-medium text-ink mb-2">Members</h2>
                {members.length === 0 ? (
                  <p className="text-sm text-mute">No members listed.</p>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Member</TableHead>
                          <TableHead>Role</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {members.map((m) => {
                          const avatar =
                            m.avatar_url ||
                            `https://github.com/${encodeURIComponent(m.user_id)}.png?size=64`;
                          const title = m.display_name || m.user_id;
                          const href = `/users/${encodeURIComponent(m.user_id)}`;
                          return (
                            <TableRow
                              key={m.user_id}
                              className="cursor-pointer"
                              onClick={() => navigate(href)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  navigate(href);
                                }
                              }}
                              tabIndex={0}
                              role="link"
                            >
                              <TableCell>
                                <div className="flex items-center gap-3 min-w-0">
                                  <img
                                    src={avatar}
                                    alt=""
                                    width={36}
                                    height={36}
                                    className="h-9 w-9 rounded-full bg-canvas-soft border border-hairline shrink-0 object-cover"
                                    loading="lazy"
                                  />
                                  <div className="min-w-0 leading-tight">
                                    <div className="text-sm font-medium text-ink truncate">
                                      {title}
                                    </div>
                                    <div className="text-xs font-mono text-mute truncate">
                                      @{m.user_id}
                                    </div>
                                  </div>
                                </div>
                              </TableCell>
                              <TableCell className="text-sm capitalize text-body">
                                {m.role}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="text-sm font-medium text-ink mb-2">Datasets</h2>
                {datasets.length === 0 ? (
                  <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                    No datasets published under this org yet.
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Dataset</TableHead>
                          <TableHead>Version</TableHead>
                          <TableHead>Visibility</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {datasets.map((d) => {
                          const href = `/datasets/${encodeDatasetId(d.dataset_id)}`;
                          return (
                            <TableRow
                              key={d.dataset_id}
                              className="cursor-pointer"
                              onClick={() => navigate(href)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  navigate(href);
                                }
                              }}
                              tabIndex={0}
                              role="link"
                            >
                              <TableCell className="font-mono text-sm">
                                {d.dataset_id}
                              </TableCell>
                              <TableCell className="font-mono text-xs text-body">
                                {d.version}
                              </TableCell>
                              <TableCell className="text-sm text-body">
                                {d.visibility}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="text-sm font-medium text-ink mb-2">Plugins</h2>
                {plugins.length === 0 ? (
                  <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                    No plugins published under this org yet.
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Plugin</TableHead>
                          <TableHead>Version</TableHead>
                          <TableHead>Visibility</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {plugins.map((p) => {
                          const href = `/plugins/${encodeDatasetId(p.dataset_id)}`;
                          return (
                            <TableRow
                              key={p.dataset_id}
                              className="cursor-pointer"
                              onClick={() => navigate(href)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  navigate(href);
                                }
                              }}
                              tabIndex={0}
                              role="link"
                            >
                              <TableCell>
                                <span className="inline-flex items-center gap-1.5 font-mono text-sm min-w-0">
                                  <span className="truncate">
                                    {packageDisplayTitle(
                                      p.dataset_id,
                                      p.display_name,
                                    )}
                                  </span>
                                  {p.official ? <OfficialMark /> : null}
                                </span>
                              </TableCell>
                              <TableCell className="font-mono text-xs text-body">
                                {p.version}
                              </TableCell>
                              <TableCell className="text-sm text-body">
                                {p.visibility}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="text-sm font-medium text-ink mb-2">
                  Shared results
                </h2>
                <p className="text-xs text-mute mb-2">
                  Suite results explicitly shared with this organization
                  (visible to you).
                </p>
                {sharedSuites.length === 0 ? (
                  <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                    No suite results have been shared with this organization
                    yet.
                  </div>
                ) : (
                  <div className="rounded-[8px] border border-hairline overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow className="hover:bg-transparent">
                          <TableHead>Suite</TableHead>
                          <TableHead>Dataset</TableHead>
                          <TableHead>By</TableHead>
                          <TableHead>Updated</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sharedSuites.map((s) => (
                          <TableRow key={s.suite_run_id}>
                            <TableCell className="font-mono text-xs">
                              {s.suite_run_id}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-body">
                              {s.dataset_id ? (
                                <Link
                                  to={`/datasets/${encodeDatasetId(s.dataset_id)}`}
                                  className="hover:underline"
                                >
                                  {s.dataset_id}
                                </Link>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                            <TableCell className="font-mono text-xs text-mute">
                              {s.uploaded_by ? `@${s.uploaded_by}` : "—"}
                            </TableCell>
                            <TableCell className="text-xs text-mute">
                              {typeof s.created_at === "number"
                                ? formatDate(
                                    new Date(s.created_at * 1000).toISOString(),
                                  )
                                : typeof s.created_at === "string"
                                  ? formatDate(s.created_at)
                                  : "—"}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>
            </div>
          ) : (
            <div className="space-y-8">
              <section>
                <h2 className="text-sm font-medium text-ink mb-1">
                  Organization description
                </h2>
                <p className="text-sm text-mute">
                  No description field on Registry yet. Display name:{" "}
                  <span className="text-body">
                    {org?.display_name || org?.name || "—"}
                  </span>
                  .
                </p>
              </section>

              {(org?.role || "").toLowerCase() === "owner" ? (
                <section className="space-y-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-medium text-ink">Members</h2>
                    <HoverTip content="Add member by GitHub Id">
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        className="shrink-0"
                        aria-label="Add member by GitHub Id"
                        onClick={() => {
                          setAddOpen(true);
                          setMemberError(null);
                        }}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </HoverTip>
                  </div>
                  {memberError && !addOpen ? (
                    <p className="text-sm text-error">{memberError}</p>
                  ) : null}
                  {members.length === 0 ? (
                    <p className="text-sm text-mute">No members listed.</p>
                  ) : (
                    <div className="rounded-[8px] border border-hairline overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow className="hover:bg-transparent">
                            <TableHead>Member</TableHead>
                            <TableHead>Role</TableHead>
                            <TableHead className="text-right w-[1%]">
                              Actions
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {members.map((m) => {
                            const isSelf = m.user_id === selfLogin;
                            const lastOwner =
                              m.role === "owner" && ownerCount <= 1;
                            const roleBusy = memberBusy === `role:${m.user_id}`;
                            const removeKey = `remove:${m.user_id}`;
                            const transferKey = `transfer:${m.user_id}`;
                            return (
                              <TableRow key={m.user_id}>
                                <TableCell>
                                  <div className="min-w-0 leading-tight">
                                    <div className="text-sm font-medium text-ink truncate">
                                      {m.display_name || m.user_id}
                                      {isSelf ? (
                                        <span className="ml-2 text-xs font-normal text-mute">
                                          you
                                        </span>
                                      ) : null}
                                    </div>
                                    <div className="text-xs font-mono text-mute truncate">
                                      @{m.user_id}
                                    </div>
                                  </div>
                                </TableCell>
                                <TableCell>
                                  <Select
                                    value={m.role === "owner" ? "owner" : "member"}
                                    disabled={roleBusy || lastOwner}
                                    onValueChange={(next) => {
                                      if (
                                        next !== "owner" &&
                                        next !== "member"
                                      ) {
                                        return;
                                      }
                                      if (next === m.role) return;
                                      void changeRole(m.user_id, next);
                                    }}
                                  >
                                    <SelectTrigger
                                      aria-label={`Role for ${m.user_id}`}
                                      className="h-8 min-w-[7rem] w-auto"
                                    >
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent className="w-max min-w-0">
                                      <SelectItem value="owner">owner</SelectItem>
                                      <SelectItem value="member">member</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </TableCell>
                                <TableCell className="text-right">
                                  <div className="flex justify-end gap-2">
                                    {!isSelf ? (
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        disabled={memberBusy === transferKey}
                                        onClick={() =>
                                          void confirmMemberAction(
                                            transferKey,
                                            () => transferTo(m.user_id),
                                          )
                                        }
                                      >
                                        {memberBusy === transferKey
                                          ? "…"
                                          : memberConfirm === transferKey
                                            ? "Confirm"
                                            : "Transfer"}
                                      </Button>
                                    ) : null}
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      className={
                                        memberConfirm === removeKey
                                          ? "border-transparent bg-error/15 text-error hover:bg-error/25 hover:text-error"
                                          : undefined
                                      }
                                      disabled={
                                        lastOwner || memberBusy === removeKey
                                      }
                                      onClick={() =>
                                        void confirmMemberAction(
                                          removeKey,
                                          () => removeMember(m.user_id),
                                        )
                                      }
                                    >
                                      {memberBusy === removeKey
                                        ? "…"
                                        : memberConfirm === removeKey
                                          ? "Confirm"
                                          : "Remove"}
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </section>
              ) : null}

              {(org?.role || "").toLowerCase() === "owner" ? (
                <section className="space-y-4">
                  <h2 className="text-sm font-medium text-ink">Invite keys</h2>

                  <div className="flex flex-wrap items-end gap-3">
                    <div className="w-full sm:w-40">
                      <label className="text-xs font-medium text-mute uppercase tracking-wide">
                        Max uses
                      </label>
                      <Input
                        type="number"
                        min={1}
                        placeholder="Unlimited"
                        value={maxUses}
                        onChange={(e) => setMaxUses(e.target.value)}
                        className="mt-1.5"
                        disabled={createBusy}
                      />
                    </div>
                    <div className="w-full sm:w-40">
                      <label className="text-xs font-medium text-mute uppercase tracking-wide">
                        Expires (days)
                      </label>
                      <Input
                        type="number"
                        min={0}
                        step="any"
                        placeholder="7"
                        value={expiresDays}
                        onChange={(e) => setExpiresDays(e.target.value)}
                        className="mt-1.5"
                        disabled={createBusy}
                      />
                    </div>
                    <p className="text-xs text-mute pb-2 flex-1 min-w-0">
                      Empty max uses = unlimited · 0 days = no expiry
                    </p>
                    <Button
                      type="button"
                      className="shrink-0"
                      disabled={createBusy}
                      onClick={() => {
                        void (async () => {
                          if (!token) return;
                          setCreateBusy(true);
                          setCreateError(null);
                          try {
                            const body: {
                              max_uses?: number;
                              expires_in_days?: number;
                            } = {};
                            const mu = maxUses.trim();
                            if (mu) {
                              const n = Number(mu);
                              if (!Number.isFinite(n) || n < 1) {
                                throw new Error("max uses must be >= 1");
                              }
                              body.max_uses = Math.floor(n);
                            }
                            const ed = expiresDays.trim();
                            if (ed && Number(ed) > 0) {
                              body.expires_in_days = Number(ed);
                            }
                            const created = await createOrgInviteKey(
                              orgId,
                              body,
                              token,
                            );
                            const full = (created.invite_key || "").trim();
                            if (!full) {
                              throw new Error(
                                "create response missing invite_key",
                              );
                            }
                            setRevealedKey(full);
                            setRevealCopied(false);
                            const keys = activeInviteKeys(
                              await listOrgInviteKeys(orgId, token),
                            );
                            setInviteKeys(keys);
                          } catch (err: unknown) {
                            if (err instanceof RegistryHttpError) {
                              setCreateError(`${err.code}: ${err.message}`);
                            } else {
                              setCreateError(
                                err instanceof Error
                                  ? err.message
                                  : String(err),
                              );
                            }
                          } finally {
                            setCreateBusy(false);
                          }
                        })();
                      }}
                    >
                      {createBusy ? "Creating…" : "Create key"}
                    </Button>
                  </div>

                  {createError ? (
                    <p className="text-sm text-error">{createError}</p>
                  ) : null}
                  {inviteLoadError ? (
                    <p className="text-sm text-error">{inviteLoadError}</p>
                  ) : null}

                  {inviteKeys.length === 0 ? (
                    <div className="rounded-[8px] border border-dashed border-hairline p-8 text-sm text-mute">
                      No invite keys yet. Create one to reveal the secret once.
                    </div>
                  ) : (
                    <div className="rounded-[8px] border border-hairline overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow className="hover:bg-transparent">
                            <TableHead>Key</TableHead>
                            <TableHead>Uses</TableHead>
                            <TableHead>Expires</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead className="text-right w-[1%]">
                              Actions
                            </TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {inviteKeys.map((k) => {
                            const display = k.token_prefix;
                            const uses =
                              k.max_uses == null
                                ? `${k.use_count ?? 0} / ∞`
                                : `${k.use_count ?? 0} / ${k.max_uses}`;
                            const exp =
                              k.expires_at == null
                                ? "never"
                                : formatDate(
                                    new Date(k.expires_at * 1000).toISOString(),
                                  );
                            const status =
                              k.active === false ? "inactive" : "active";
                            const confirmDelete = confirmDeleteId === k.key_id;
                            return (
                              <TableRow key={k.key_id}>
                                <TableCell className="font-mono text-xs max-w-[min(40rem,50vw)]">
                                  <HoverTip content={display}>
                                    <span className="block truncate">
                                      {display}
                                    </span>
                                  </HoverTip>
                                </TableCell>
                                <TableCell className="text-sm tabular-nums">
                                  {uses}
                                </TableCell>
                                <TableCell className="text-xs text-mute">
                                  {exp}
                                </TableCell>
                                <TableCell className="text-sm capitalize text-body">
                                  {status}
                                </TableCell>
                                <TableCell className="text-right">
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className={
                                      confirmDelete
                                        ? "border-transparent bg-error/15 text-error hover:bg-error/25 hover:text-error"
                                        : undefined
                                    }
                                    disabled={revokeBusy === k.key_id}
                                    onClick={() => {
                                      if (confirmDeleteId !== k.key_id) {
                                        setConfirmDeleteId(k.key_id);
                                        return;
                                      }
                                      void (async () => {
                                        if (!token) return;
                                        setRevokeBusy(k.key_id);
                                        try {
                                          await revokeOrgInviteKey(
                                            orgId,
                                            k.key_id,
                                            token,
                                          );
                                          setConfirmDeleteId(null);
                                          setInviteKeys((prev) =>
                                            prev.filter(
                                              (row) => row.key_id !== k.key_id,
                                            ),
                                          );
                                        } finally {
                                          setRevokeBusy(null);
                                        }
                                      })();
                                    }}
                                  >
                                    {revokeBusy === k.key_id
                                      ? "…"
                                      : confirmDelete
                                        ? "Confirm"
                                        : "Delete"}
                                  </Button>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  )}
                </section>
              ) : (
                <section>
                  <h2 className="text-sm font-medium text-ink mb-1">
                    Invite keys
                  </h2>
                  <p className="text-sm text-mute">
                    Only org owners can create and manage invite keys.
                  </p>
                </section>
              )}

              <section>
                <h2 className="text-sm font-medium text-ink mb-1">Secrets</h2>
                <div className="rounded-[8px] border border-dashed border-hairline p-6 text-sm text-mute">
                  Organization-scoped secrets (API keys for hosted jobs) are not
                  implemented in AGEVAL Registry. Use host env / CLI credentials
                  instead.
                </div>
              </section>

              <section className="pt-4 border-t border-hairline">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium text-ink">
                      {isOwner ? "Dissolve organization" : "Leave organization"}
                    </h2>
                    <p className="text-sm text-mute mt-0.5">
                      {isOwner
                        ? "Permanently delete this org, members, and invite keys. Fails if packages are still published under it."
                        : "Remove yourself from this organization. You can rejoin later with an invite key."}
                    </p>
                    {dangerError ? (
                      <p className="text-sm text-error mt-2">{dangerError}</p>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    className={
                      dangerConfirm
                        ? "shrink-0 border-transparent bg-error/15 text-error hover:bg-error/25 hover:text-error"
                        : "shrink-0"
                    }
                    disabled={dangerBusy}
                    onClick={() => {
                      if (!dangerConfirm) {
                        setDangerConfirm(true);
                        setDangerError(null);
                        return;
                      }
                      void (async () => {
                        if (!token) return;
                        setDangerBusy(true);
                        setDangerError(null);
                        try {
                          if (isOwner) {
                            await dissolveOrg(orgId, token);
                          } else {
                            await leaveOrg(orgId, token);
                          }
                          navigate("/organizations");
                        } catch (err: unknown) {
                          if (err instanceof RegistryHttpError) {
                            setDangerError(`${err.code}: ${err.message}`);
                          } else {
                            setDangerError(
                              err instanceof Error ? err.message : String(err),
                            );
                          }
                          setDangerConfirm(false);
                        } finally {
                          setDangerBusy(false);
                        }
                      })();
                    }}
                  >
                    {dangerBusy
                      ? "…"
                      : dangerConfirm
                        ? "Confirm"
                        : isOwner
                          ? "Dissolve"
                          : "Leave"}
                  </Button>
                </div>
              </section>
            </div>
          )}
        </>
      )}

      {addOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-member-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !addBusy) {
              setAddOpen(false);
              setMemberError(null);
            }
          }}
        >
          <div className="w-full max-w-md rounded-[12px] border border-hairline bg-canvas shadow-lg p-5 space-y-4">
            <div>
              <h2
                id="add-member-title"
                className="text-lg font-semibold tracking-tight text-ink"
              >
                Add member
              </h2>
              <p className="text-sm text-mute mt-1">
                Add by GitHub Id. They join as a member; change the role
                after if needed.
              </p>
            </div>
            <div>
              <label
                htmlFor="add-member-login"
                className="text-xs font-medium text-mute uppercase tracking-wide"
              >
                GitHub Id
              </label>
              <Input
                id="add-member-login"
                value={addLogin}
                onChange={(e) => setAddLogin(e.target.value)}
                placeholder="alice"
                className="mt-1.5 font-mono text-sm"
                autoFocus
                disabled={addBusy}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void addMember();
                  }
                }}
              />
            </div>
            {memberError ? (
              <p className="text-sm text-error">{memberError}</p>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={addBusy}
                onClick={() => {
                  setAddOpen(false);
                  setMemberError(null);
                }}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={addBusy || !addLogin.trim()}
                onClick={() => void addMember()}
              >
                {addBusy ? "Adding…" : "Add member"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {revealedKey ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="invite-key-reveal-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setRevealedKey(null);
              setRevealCopied(false);
            }
          }}
        >
          <div className="w-full max-w-lg rounded-[12px] border border-hairline bg-canvas shadow-lg p-5 space-y-4">
            <div>
              <h2
                id="invite-key-reveal-title"
                className="text-lg font-semibold tracking-tight text-ink"
              >
                Invite key created
              </h2>
              <p className="text-sm text-mute mt-1">
                This is the only time the full key is shown. Copy and store it
                somewhere safe — you cannot view it again.
              </p>
            </div>
            <div className="rounded-[8px] border border-hairline bg-canvas-soft/40 px-3 py-2.5">
              <code className="block font-mono text-sm text-ink break-all select-all">
                {revealedKey}
              </code>
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  void navigator.clipboard?.writeText(revealedKey).then(() => {
                    setRevealCopied(true);
                    window.setTimeout(() => setRevealCopied(false), 1500);
                  });
                }}
              >
                {revealCopied ? "Copied" : "Copy"}
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setRevealedKey(null);
                  setRevealCopied(false);
                }}
              >
                Done
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
