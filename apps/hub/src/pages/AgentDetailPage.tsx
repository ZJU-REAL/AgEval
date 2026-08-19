import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { DisplayNameEditor } from "@/components/display-name-editor";
import { OfficialMark } from "@/components/official-mark";
import { FileSplitPanel } from "@/components/file-split-panel";
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
  getOrg,
  getPackageByDigest,
  getPackageFile,
  listPackageFiles,
  listPackageVersionsWithAppearances,
  splitPackageId,
  updatePackageDisplayName,
  type AgentAppearance,
  type AgentPreview,
  type FileItem,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, pathMatchesPrefixes, type TreeNode } from "@/lib/file-tree";
import { formatScore } from "@/lib/utils";

export function AgentDetailPage() {
  const { agentId: rawId } = useParams();
  const agentId = decodeDatasetId(rawId || "");
  const token = getToken();

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [preview, setPreview] = useState<AgentPreview | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [canEditName, setCanEditName] = useState(false);
  const [appearances, setAppearances] = useState<AgentAppearance[]>([]);
  const [versions, setVersions] = useState<PackageRelease[]>([]);
  const [selectedAppearanceKey, setSelectedAppearanceKey] = useState<string | null>(
    null,
  );
  const [overlayItems, setOverlayItems] = useState<FileItem[]>([]);
  const [overlayPath, setOverlayPath] = useState<string | null>(null);
  const [overlayContent, setOverlayContent] = useState<string | null>(null);
  const [overlayNote, setOverlayNote] = useState<string | null>(null);
  const [overlayTreeLoading, setOverlayTreeLoading] = useState(false);
  const [overlayFileLoading, setOverlayFileLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setTreeLoading(true);
      setError(null);
      try {
        const listed = await listPackageVersionsWithAppearances(agentId, token);
        const versions = listed.items;
        if (!versions.length) {
          throw new RegistryHttpError(404, "not_found", "agent not found");
        }
        setVersions(versions);
        setAppearances(listed.appearances);
        const latest = [...versions].sort(
          (a, b) => (b.created_at ?? 0) - (a.created_at ?? 0),
        )[0];
        if (cancelled) return;

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
        setAppearances([]);
        setVersions([]);
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
  }, [agentId, token]);

  useEffect(() => {
    if (!release || !selectedPath) {
      setFileContent(null);
      setFileNote(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    setFileNote(null);
    getPackageFile(agentId, release.package_digest, selectedPath, token)
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
  }, [agentId, release, selectedPath, token]);

  const installCmd = useMemo(() => {
    if (!release) return `bora agent install ${agentId}@<version>`;
    return `bora agent install ${agentId}@${release.version}`;
  }, [agentId, release]);

  const runCmd = useMemo(() => {
    const ver = release?.version || "<version>";
    return `bora run <dataset> --agent ${agentId}@${ver}`;
  }, [agentId, release]);

  const formatBadge =
    preview?.format || (release?.package_kind === "agent" ? "bora.agent/1" : null);

  const packageParts = useMemo(() => splitPackageId(agentId), [agentId]);

  const bindingRows = useMemo(() => {
    const binding = preview?.binding || {};
    return Object.entries(binding).filter(([, v]) => v !== null && v !== undefined);
  }, [preview]);

  const appearancesByVersion = useMemo(() => {
    const groups = new Map<string, AgentAppearance[]>();
    for (const row of appearances) {
      const key = row.agent_version || "unknown";
      const list = groups.get(key) ?? [];
      list.push(row);
      groups.set(key, list);
    }
    return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a));
  }, [appearances]);

  const selectedAppearance = useMemo(() => {
    if (!appearances.length) return null;
    return (
      appearances.find(
        (row) => `${row.suite_run_id}:${row.role}` === selectedAppearanceKey,
      ) ?? appearances[0]
    );
  }, [appearances, selectedAppearanceKey]);

  const overlayDigest = useMemo(() => {
    if (!selectedAppearance) return "";
    const match = versions.find((row) => row.version === selectedAppearance.agent_version);
    return match?.package_digest || "";
  }, [selectedAppearance, versions]);

  const overlayKey = (selectedAppearance?.overlays ?? []).join("\n");
  const overlayPrefixes = overlayKey ? overlayKey.split("\n") : [];
  const canPreviewOverlays = Boolean(overlayDigest && overlayPrefixes.length);

  useEffect(() => {
    if (!canPreviewOverlays || !overlayDigest) {
      setOverlayItems([]);
      setOverlayPath(null);
      setOverlayContent(null);
      setOverlayNote(null);
      setOverlayTreeLoading(false);
      return;
    }
    let cancelled = false;
    setOverlayTreeLoading(true);
    listPackageFiles(agentId, overlayDigest, token)
      .then((files) => {
        if (cancelled) return;
        const matched = files.items.filter(
          (item) => item.type !== "dir" && pathMatchesPrefixes(item.path, overlayPrefixes),
        );
        setOverlayItems(matched);
        const prefer =
          overlayPrefixes
            .map((prefix) =>
              matched.find((item) => item.path === prefix || item.path.startsWith(`${prefix}/`)),
            )
            .find(Boolean) || matched[0];
        setOverlayPath(prefer?.path ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setOverlayItems([]);
        setOverlayPath(null);
        setOverlayNote(
          err instanceof RegistryHttpError
            ? `${err.code}: ${err.message}`
            : err instanceof Error
              ? err.message
              : String(err),
        );
      })
      .finally(() => {
        if (!cancelled) setOverlayTreeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, canPreviewOverlays, overlayDigest, overlayKey, token]);

  const overlayTree = useMemo(
    () => (canPreviewOverlays ? buildNestedTree(overlayItems, "overlays") : []),
    [canPreviewOverlays, overlayItems],
  );

  useEffect(() => {
    if (!canPreviewOverlays || !overlayDigest || !overlayPath) {
      setOverlayContent(null);
      return;
    }
    let cancelled = false;
    setOverlayFileLoading(true);
    getPackageFile(agentId, overlayDigest, overlayPath, token)
      .then((file) => {
        if (cancelled) return;
        try {
          setOverlayContent(decodeFileContent(file));
          setOverlayNote(null);
        } catch {
          setOverlayContent(null);
          setOverlayNote("Could not decode file content.");
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setOverlayContent(null);
        setOverlayNote(
          err instanceof RegistryHttpError
            ? `${err.code}: ${err.message}`
            : err instanceof Error
              ? err.message
              : String(err),
        );
      })
      .finally(() => {
        if (!cancelled) setOverlayFileLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, canPreviewOverlays, overlayDigest, overlayPath, token]);

  return (
    <>
      <BreadcrumbNav
        items={[{ label: "Agent hub", href: "/agents" }, { label: agentId || "…" }]}
        className="mb-4"
      />

      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <DisplayNameEditor
            value={
              release?.display_name?.trim() ||
              preview?.label?.trim() ||
              packageParts.name
            }
            prefix={packageParts.org ? `${packageParts.org}/` : null}
            canEdit={Boolean(token && canEditName && release)}
            headingClassName="text-xl font-semibold tracking-tight text-ink"
            afterTitle={release?.official ? <OfficialMark /> : null}
            onSave={async (next) => {
              const updated = await updatePackageDisplayName(agentId, next, token);
              setRelease((prev) =>
                prev ? { ...prev, display_name: updated.display_name || next } : prev,
              );
            }}
          />
          {formatBadge ? (
            <span className="text-[11px] font-medium font-mono px-2 py-0.5 rounded border border-hairline bg-canvas-soft text-body">
              {formatBadge}
            </span>
          ) : null}
        </div>
        {release ? (
          <p className="text-sm text-mute mt-1">
            <span className="font-mono">@{agentId}</span>
            {" · "}
            v{release.version} · {release.visibility}
            {release.org_id ? (
              <>
                {" "}
                · org{" "}
                <span className="inline-flex items-center gap-1">
                  <Link
                    to={`/organizations/${encodeURIComponent(release.org_id)}`}
                    className="font-mono text-xs text-body hover:text-ink"
                  >
                    {release.org_id}
                  </Link>
                  {release.official ? <OfficialMark kind="org" /> : null}
                </span>
              </>
            ) : null}
          </p>
        ) : null}
        {preview?.description ? (
          <p className="text-sm text-body mt-2 max-w-2xl">{preview.description}</p>
        ) : null}
        {preview?.tags?.length ? (
          <p className="mt-2 flex flex-wrap gap-1.5">
            {preview.tags.map((t) => (
              <span
                key={t}
                className="text-[11px] font-mono px-1.5 py-0.5 rounded border border-hairline bg-canvas-soft text-mute"
              >
                {t}
              </span>
            ))}
          </p>
        ) : null}
      </div>

      {loading && <p className="text-sm text-mute">Loading…</p>}
      {error && (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load agent</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
          <p className="mt-3">
            <Link to="/agents" className="underline underline-offset-2 text-body">
              ← Back to Agent hub
            </Link>
          </p>
        </div>
      )}

      {!loading && !error && release && (
        <div className="space-y-6">
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Install &amp; run (CLI)</h2>
            <CommandStrip command={installCmd} />
            <CommandStrip command={runCmd} />
            <p className="text-xs text-mute">
              Install writes only the local cache; the binding applies per run via{" "}
              <span className="font-mono">--agent</span> and lands in the lock&apos;s
              job_overlay as <span className="font-mono">agent_ref</span> (provenance,
              not fingerprint identity).
            </p>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Job binding</h2>
            {bindingRows.length === 0 ? (
              <p className="text-sm text-mute">No binding preview available.</p>
            ) : (
              <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4">
                <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm">
                  {bindingRows.map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="font-mono text-xs text-mute pt-0.5">{key}</dt>
                      <dd className="font-mono text-xs text-body break-all">
                        {typeof value === "string"
                          ? value
                          : JSON.stringify(value, null, 1)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-sm font-medium text-ink">Appearances</h2>
            <p className="text-xs text-mute">
              Official public complete release-bound suites that named this Agent
              via <span className="font-mono">agent_ref</span>. Observational
              metrics only — PASS stays on the independent evaluator.
            </p>
            {appearancesByVersion.length === 0 ? (
              <p className="text-sm text-mute">
                No Hub appearances yet. Run with{" "}
                <span className="font-mono">--agent {agentId}@&lt;version&gt;</span>{" "}
                and upload a complete official suite.
              </p>
            ) : (
              appearancesByVersion.map(([version, rows]) => (
                <div key={version} className="space-y-2">
                  <h3 className="text-xs font-mono text-mute">v{version}</h3>
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
                          const selected =
                            (selectedAppearanceKey ??
                              `${appearances[0]?.suite_run_id}:${appearances[0]?.role}`) ===
                            key;
                          return (
                            <TableRow
                              key={key}
                              className="cursor-pointer"
                              data-state={selected ? "open" : undefined}
                              onClick={() => setSelectedAppearanceKey(key)}
                            >
                              <TableCell className="font-mono text-xs">
                                <Link
                                  to={`/datasets/${encodeDatasetId(row.database_id)}?tab=leaderboard&suite=${encodeURIComponent(row.suite_run_id)}`}
                                  onClick={(e) => e.stopPropagation()}
                                  className="hover:underline underline-offset-2"
                                >
                                  {row.database_id}
                                </Link>
                              </TableCell>
                              <TableCell className="font-mono text-xs">
                                {row.role}
                              </TableCell>
                              <TableCell className="font-mono text-xs">
                                {row.model || "—"}
                              </TableCell>
                              <TableCell className="text-right tabular-nums text-xs">
                                {formatScore(row.pass_rate)}
                              </TableCell>
                              <TableCell className="text-right tabular-nums text-xs">
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
            {canPreviewOverlays ? (
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-ink">Published overlays</h3>
                <p className="text-xs text-mute">
                  Prefix closure from this Agent package, not the Dataset.
                </p>
                <div className="rounded-[8px] border border-hairline overflow-hidden">
                  <FileSplitPanel
                    tree={overlayTree}
                    treeLoading={overlayTreeLoading}
                    selectedPath={overlayPath}
                    onSelect={setOverlayPath}
                    fileContent={overlayContent}
                    fileLoading={overlayFileLoading}
                    fileNote={overlayNote}
                    rootPrefix="overlays"
                  />
                </div>
              </div>
            ) : null}
          </section>

          <section id="agent-files" className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Files</h2>
            <p className="text-xs text-mute">
              Read-only preview of this package, including any bundled{" "}
              <span className="font-mono">overlays/</span> files. Locator names
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
        </div>
      )}
    </>
  );
}
