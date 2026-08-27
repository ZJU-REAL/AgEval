import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BindingPreview } from "@/components/binding-preview";
import { LoadingState } from "@/components/empty-state";
import { BrandMark } from "@/components/brand-mark";
import { BuiltinMark } from "@/components/builtin-mark";
import { MarketplaceCounts } from "@/components/marketplace-counts";
import { CatalogHead } from "@/components/page-head";
import { PackageStarButton } from "@/components/star-toggle";
import { CommandStrip } from "@/components/command-strip";
import { DisplayNameEditor } from "@/components/display-name-editor";
import { EntityMarkControl } from "@/components/entity-mark-control";
import { entityHintFromPackage, markFromPackage } from "@/lib/brand-marks";
import { OfficialMark } from "@/components/official-mark";
import { FileSplitPanel } from "@/components/file-split-panel";
import { PackageOwnerOps } from "@/components/package-owner-ops";
import { InlineMarkdown } from "@/components/markdown";
import { UnderlineTabs } from "@/components/underline-tabs";
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
  decodeDatasetId,
  decodeFileContent,
  encodeDatasetId,
  getBuiltinPackageFile,
  getOrg,
  getPackageByDigest,
  getPackageFile,
  isBuiltinPackage,
  isDraftRelease,
  listBuiltinPackageFiles,
  listPackageFiles,
  listPackageVersions,
  listPackageVersionsWithAppearances,
  splitPackageId,
  updatePackageDisplayName,
  type AgentAppearance,
  type AgentPreview,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import {
  bindingModel,
  formatAgentRunCommand,
  registeredModels,
} from "@/lib/agent-models";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";
import { cn, formatScore } from "@/lib/utils";

type AgentTab = "overview" | "appearances" | "files";

function parseAgentTab(raw: string | null): AgentTab {
  if (raw === "appearances" || raw === "files") return raw;
  return "overview";
}

export function AgentDetailPage() {
  const { agentId: rawId } = useParams();
  const agentId = decodeDatasetId(rawId || "");
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedModel = (searchParams.get("model") || "").trim();
  const pageTab = parseAgentTab(searchParams.get("tab"));
  const token = getToken();
  const navigate = useNavigate();
  const [reloadAt, setReloadAt] = useState(0);

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [preview, setPreview] = useState<AgentPreview | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [canEditName, setCanEditName] = useState(false);
  const [appearances, setAppearances] = useState<AgentAppearance[]>([]);
  const [modelQuery, setModelQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setTreeLoading(true);
      setError(null);
      try {
        const listed = await listPackageVersionsWithAppearances(agentId, token, {
          packageKind: "agent",
        });
        const versions = listed.items;
        if (!versions.length) {
          throw new RegistryHttpError(404, "not_found", "agent not found");
        }
        setAppearances(listed.appearances);
        const latest = [...versions].sort(
          (a, b) => (b.created_at ?? 0) - (a.created_at ?? 0),
        )[0];
        if (cancelled) return;

        if (isBuiltinPackage(latest)) {
          setRelease(latest);
          setPreview(latest.agent_preview || null);
          setCanEditName(false);
          const files = await listBuiltinPackageFiles(agentId, token, {
            packageKind: "agent",
          });
          if (cancelled) return;
          const nested = buildNestedTree(files.items);
          setTree(nested);
          setFilePaths(files.items.filter((e) => e.type !== "dir").map((e) => e.path));
          const prefer =
            files.items.find((e) => e.path === "agent.yaml") ||
            files.items.find((e) => e.path === "README.md") ||
            files.items.find((e) => e.type !== "dir");
          if (prefer) setSelectedPath(prefer.path);
          return;
        }

        let meta: PackageRelease = latest;
        try {
          meta = await getPackageByDigest(agentId, latest.package_digest, token);
        } catch {
          /* list meta is enough for non-preview fields */
        }
        if (cancelled) return;

        if (meta.package_kind && meta.package_kind !== "agent") {
          throw new RegistryHttpError(
            404,
            "not_found",
            "not an agent package (use Datasets / Plugins for other kinds)",
          );
        }

        setRelease(meta);
        setPreview(meta.agent_preview || null);
        if (token && meta.org_id) {
          try {
            const org = await getOrg(meta.org_id, token);
            if (!cancelled) {
              setCanEditName((org.role || "").toLowerCase() === "owner");
            }
          } catch {
            if (!cancelled) setCanEditName(false);
          }
        } else if (!cancelled) {
          setCanEditName(false);
        }

        const files = await listPackageFiles(agentId, latest.package_digest, token);
        if (cancelled) return;
        const nested = buildNestedTree(files.items);
        setTree(nested);
        setFilePaths(files.items.filter((e) => e.type !== "dir").map((e) => e.path));
        const prefer =
          files.items.find((e) => e.path === "agent.yaml") ||
          files.items.find((e) => e.path === "README.md") ||
          files.items.find((e) => e.type !== "dir");
        if (prefer) setSelectedPath(prefer.path);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setRelease(null);
        setPreview(null);
        setTree([]);
        setFilePaths([]);
        setAppearances([]);
      } finally {
        if (!cancelled) {
          setLoading(false);
          setTreeLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [agentId, token, reloadAt]);

  const packageDigest = release?.package_digest;
  const builtin = isBuiltinPackage(release);

  useEffect(() => {
    if (!selectedPath || (!builtin && !packageDigest)) {
      setFileContent(null);
      setFileNote(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    setFileNote(null);
    const pending = builtin
      ? getBuiltinPackageFile(agentId, selectedPath, token, {
          packageKind: "agent",
        })
      : getPackageFile(agentId, packageDigest || "", selectedPath, token);
    pending
      .then((f) => {
        if (cancelled) return;
        try {
          setFileContent(decodeFileContent(f));
        } catch {
          setFileContent(null);
          setFileNote("Could not decode file content.");
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setFileContent(null);
        if (err instanceof RegistryHttpError) {
          setFileNote(`${err.code}: ${err.message}`);
        } else {
          setFileNote(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, packageDigest, selectedPath, token, builtin]);

  const installCmd = useMemo(() => {
    if (!release) return `ageval agent install ${agentId}@<version>`;
    return `ageval agent install ${agentId}@${release.version}`;
  }, [agentId, release]);

  const runCmd = useMemo(
    () =>
      formatAgentRunCommand(
        agentId,
        release?.version || "<version>",
        selectedModel,
        { builtin },
      ),
    [agentId, release, selectedModel, builtin],
  );

  const formatBadge =
    preview?.format || (release?.package_kind === "agent" ? "ageval.agent/1" : null);

  const packageParts = useMemo(() => splitPackageId(agentId), [agentId]);

  const binding = (preview?.binding || {}) as Record<string, unknown>;
  const hasBinding = Object.keys(binding).length > 0;
  const defaultModel = bindingModel(binding);
  const models = useMemo(
    () =>
      registeredModels(
        defaultModel,
        appearances.map((row) => row.model),
        selectedModel,
      ),
    [appearances, defaultModel, selectedModel],
  );
  const shownModels = useMemo(() => {
    const q = modelQuery.trim().toLowerCase();
    if (!q) return models;
    return models.filter((model) => model.toLowerCase().includes(q));
  }, [models, modelQuery]);
  const visibleAppearances = useMemo(() => {
    if (!selectedModel) return appearances;
    return appearances.filter(
      (row) => (row.model || "").trim() === selectedModel,
    );
  }, [appearances, selectedModel]);

  function agentHref(next?: { model?: string | null; tab?: AgentTab }) {
    const n = new URLSearchParams();
    const model = next && "model" in next ? next.model : selectedModel;
    const tab = next?.tab ?? pageTab;
    const m = (model || "").trim();
    if (m) n.set("model", m);
    if (tab !== "overview") n.set("tab", tab);
    const qs = n.toString();
    return `/agents/${encodeDatasetId(agentId)}${qs ? `?${qs}` : ""}`;
  }

  function setTab(next: AgentTab) {
    const n = new URLSearchParams(searchParams);
    if (next === "overview") n.delete("tab");
    else n.set("tab", next);
    setSearchParams(n, { replace: true });
  }

  function openOverlayPath(declared: string) {
    const prefix = declared.endsWith("/") ? declared : `${declared}/`;
    const resolved =
      filePaths.find((p) => p === declared) ||
      filePaths.find((p) => p.startsWith(prefix)) ||
      declared;
    setSelectedPath(resolved);
    setTab("files");
  }

  const appearancesByVersion = useMemo(() => {
    const groups = new Map<string, AgentAppearance[]>();
    for (const row of visibleAppearances) {
      const key = row.agent_version || "unknown";
      const list = groups.get(key) ?? [];
      list.push(row);
      groups.set(key, list);
    }
    return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a));
  }, [visibleAppearances]);

  return (
    <>
      <CatalogHead
        title="Agent hub"
        crumbs={[
          { label: "Agent hub", href: "/agents" },
          { label: agentId || "…" },
        ]}
      />

      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <DisplayNameEditor
              value={
                release?.display_name?.trim() ||
                preview?.label?.trim() ||
                packageParts.name
              }
              prefix={packageParts.org ? `${packageParts.org}/` : null}
              canEdit={Boolean(token && canEditName && release && !builtin)}
              headingClassName="text-xl font-semibold tracking-tight text-ink"
              beforeTitle={
                builtin && release ? (
                  <BrandMark mark={markFromPackage(release)} size={24} />
                ) : release ? (
                  <EntityMarkControl
                    hint={entityHintFromPackage({
                      ...release,
                      agent_preview: preview || release.agent_preview,
                    })}
                    packageId={agentId}
                    token={token}
                    canEdit={Boolean(token && canEditName)}
                    onUpdated={(patch) => {
                      setRelease((prev) =>
                        prev
                          ? {
                              ...prev,
                              icon_key: patch.icon_key,
                              icon_github: patch.icon_github,
                            }
                          : prev,
                      );
                    }}
                  />
                ) : null
              }
              afterTitle={
                builtin ? (
                  <BuiltinMark />
                ) : release?.official ? (
                  <OfficialMark />
                ) : null
              }
              onSave={async (next) => {
                const updated = await updatePackageDisplayName(agentId, next, token);
                setRelease((prev) =>
                  prev ? { ...prev, display_name: updated.display_name || next } : prev,
                );
              }}
            />
            {formatBadge ? (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded border border-hairline bg-canvas-soft text-body">
                {formatBadge}
              </span>
            ) : null}
          </div>
          {release ? (
            <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-mute">
              <span>@{agentId}</span>
              {builtin ? null : (
                <>
                  <span aria-hidden>·</span>
                  <span>
                    {isDraftRelease(release) ? "draft" : `v${release.version}`}
                  </span>
                  <span aria-hidden>·</span>
                  <MarketplaceCounts
                    downloadCount={release.download_count}
                    favoriteCount={release.favorite_count}
                  />
                </>
              )}
              {release.org_id ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="inline-flex items-center gap-1">
                    org{" "}
                    <Link
                      to={`/organizations/${encodeURIComponent(release.org_id)}`}
                      className="text-link hover:text-link-deep"
                    >
                      {release.org_id}
                    </Link>
                    {release.official ? <OfficialMark kind="org" /> : null}
                  </span>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
        {release && !builtin ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <PackageStarButton
              packageId={agentId}
              release={release}
              onUpdated={(next) => {
                setRelease((prev) =>
                  prev
                    ? {
                        ...prev,
                        favorited: next.favorited,
                        favorite_count: next.favorite_count,
                      }
                    : prev,
                );
              }}
            />
            <PackageOwnerOps
              packageId={agentId}
              release={release}
              canManage={canEditName}
              token={token}
              onUpdated={(next) => setRelease(next)}
              onDeleted={() => {
                void listPackageVersions(agentId, token).then((rows) => {
                  if (!rows.length) navigate("/agents");
                  else setReloadAt((n) => n + 1);
                });
              }}
              onReleased={() => setReloadAt((n) => n + 1)}
            />
          </div>
        ) : null}
      </div>

      {loading && <LoadingState label="Loading agent" />}
      {error && (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load agent</p>
          <p className="mt-1 text-xs text-body">{error}</p>
          <p className="mt-3">
            <Link to="/agents" className="text-link hover:text-link-deep underline underline-offset-2">
              ← Back to Agent hub
            </Link>
          </p>
        </div>
      )}

      {!loading && !error && release && (
        <div className="space-y-6">
          {preview?.description ? (
            <InlineMarkdown source={preview.description} />
          ) : null}

          <section className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="shrink-0 text-sm font-medium text-ink">Model</h2>
              {models.length > 0 ? (
                <Input
                  value={modelQuery}
                  onChange={(e) => setModelQuery(e.target.value)}
                  placeholder="Search models…"
                  aria-label="Search models"
                  className="h-9 w-[min(100%,24rem)] max-w-sm focus-visible:border-hairline"
                />
              ) : null}
            </div>
            <p className="text-xs text-mute">
              {builtin
                ? "Models from plaza overlay runs of this harness. Selecting one is query state on this page, not a second package."
                : "Package default plus models that appeared on consented plaza suites. Selecting one is query state on this harness page, not a second package."}
            </p>
            {models.length === 0 ? (
              <p className="text-sm text-mute">
                No registered model yet. The package default is empty.
              </p>
            ) : shownModels.length === 0 ? (
              <p className="text-sm text-mute">
                No models match “{modelQuery.trim()}”.
              </p>
            ) : (
              <ul className="m-0 flex flex-wrap gap-1.5 p-0 list-none">
                {shownModels.map((model) => {
                  const selected = model === selectedModel;
                  return (
                    <li key={model}>
                      <Link
                        to={agentHref({
                          model: selected ? null : model,
                        })}
                        replace
                        aria-current={selected ? "page" : undefined}
                        className={cn(
                          "inline-flex max-w-full truncate rounded-[6px] border px-2 py-1 text-sm transition-colors duration-200 ease-smooth",
                          selected
                            ? "bg-link/10 text-ink"
                            : "border-hairline text-body hover:bg-row-hover hover:text-ink",
                        )}
                      >
                        {model}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            {builtin ? null : <CommandStrip command={installCmd} />}
            <CommandStrip command={runCmd} />
            <p className="text-xs text-mute">
              {builtin ? (
                <>
                  Ships with ageval; no install. Bind a run with{" "}
                  <span>--agent</span>. Optional <span>--model</span>{" "}
                  overrides this run&apos;s model.
                </>
              ) : (
                <>
                  Install writes only the local cache; the harness binds per run
                  via <span>--agent</span>. Optional <span>--model</span>{" "}
                  overrides this run&apos;s model. <span>agent_ref</span> is
                  provenance, not fingerprint identity.
                </>
              )}
            </p>
          </section>

          <UnderlineTabs
            ariaLabel="Agent sections"
            value={pageTab}
            onChange={setTab}
            items={[
              { id: "overview", label: "Overview" },
              { id: "appearances", label: "Appearances" },
              { id: "files", label: "Files" },
            ]}
          />

          {pageTab === "overview" ? (
            <section className="space-y-2">
              <h2 className="text-sm font-medium text-ink">Job binding</h2>
              {hasBinding ? (
                <BindingPreview
                  binding={binding}
                  runModel={selectedModel}
                  onOpenOverlay={openOverlayPath}
                />
              ) : (
                <p className="text-sm text-mute">
                  No binding preview available.
                </p>
              )}
            </section>
          ) : null}

          {pageTab === "appearances" ? (
            <section className="space-y-3">
              <p className="text-xs text-mute">
                {builtin
                  ? "Official public complete release-bound suites whose overlay harness matches this card. Observational metrics only — PASS stays on the independent evaluator."
                  : "Official public complete release-bound suites with this Agent org’s consent (direct attach or an approved appearance request). Observational metrics only — PASS stays on the independent evaluator."}
              </p>
              {appearancesByVersion.length === 0 ? (
                <p className="text-sm text-mute">
                  {selectedModel
                    ? builtin
                      ? "No plaza appearances for this model yet."
                      : "No consented appearances for this model yet."
                    : builtin
                      ? "No plaza appearances yet. Upload a public complete suite on an official Dataset that ran this harness."
                      : (
                        <>
                          No Hub appearances yet. Attach a published{" "}
                          <span>org/name@version</span> as this
                          Agent’s org owner, or approve an appearance request.
                        </>
                      )}
                </p>
              ) : (
                appearancesByVersion.map(([version, rows]) => (
                  <div key={version} className="space-y-2">
                    <h3 className="text-xs text-mute">v{version}</h3>
                    <div className="rounded-[8px] border border-hairline overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Dataset</TableHead>
                            <TableHead>Role</TableHead>
                            <TableHead>Model</TableHead>
                            <TableHead className="text-right">Pass rate</TableHead>
                            <TableHead className="text-right">Mean</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {rows.map((row) => {
                            const key = `${row.suite_run_id}:${row.role}`;
                            return (
                              <TableRow key={key}>
                                <TableCell>
                                  <Link
                                    to={`/datasets/${encodeDatasetId(row.dataset_id)}?tab=leaderboard&suite=${encodeURIComponent(row.suite_run_id)}`}
                                    className="text-link hover:text-link-deep hover:underline underline-offset-2"
                                  >
                                    {row.dataset_id}
                                  </Link>
                                </TableCell>
                                <TableCell>
                                  {row.role}
                                </TableCell>
                                <TableCell>
                                  {row.model || "—"}
                                </TableCell>
                                <TableCell className="text-right tabular-nums">
                                  {formatScore(row.pass_rate)}
                                </TableCell>
                                <TableCell className="text-right tabular-nums">
                                  {formatScore(row.mean_score)}
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                ))
              )}
            </section>
          ) : null}

          {pageTab === "files" ? (
            <section className="space-y-2">
              <p className="text-xs text-mute">
                Read-only preview of this package, including any bundled{" "}
                <span>overlays/</span> files. Locator names
                only, never secret values.
              </p>
              <div className="rounded-[8px] border border-hairline overflow-hidden">
                <FileSplitPanel
                  tree={tree}
                  treeLoading={treeLoading}
                  selectedPath={selectedPath}
                  onSelect={setSelectedPath}
                  fileContent={fileContent}
                  fileLoading={fileLoading}
                  fileNote={fileNote}
                />
              </div>
            </section>
          ) : null}
        </div>
      )}
    </>
  );
}
