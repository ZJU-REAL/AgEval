import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { DisplayNameEditor } from "@/components/display-name-editor";
import { OfficialMark } from "@/components/official-mark";
import { FileSplitPanel } from "@/components/file-split-panel";
import {
  decodeDatasetId,
  decodeFileContent,
  getOrg,
  getPackageByDigest,
  getPackageFile,
  listPackageFiles,
  listPackageVersions,
  splitPackageId,
  updatePackageDisplayName,
  type AgentPreview,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";

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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setTreeLoading(true);
      setError(null);
      try {
        const versions = await listPackageVersions(agentId, token);
        if (!versions.length) {
          throw new RegistryHttpError(404, "not_found", "agent not found");
        }
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
