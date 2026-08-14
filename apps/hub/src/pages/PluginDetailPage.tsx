import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { Shell } from "@/components/layout";
import {
  declaredSlotsFromPreview,
  PluginSlotTimeline,
} from "@/components/plugin-slot-timeline";
import {
  decodeDatasetId,
  decodeFileContent,
  getPackageByDigest,
  getPackageFile,
  listPackageFiles,
  listPackageVersions,
  type PackageRelease,
  type PluginPreview,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";

export function PluginDetailPage() {
  const { pluginId: rawId } = useParams();
  const pluginId = decodeDatasetId(rawId || "");
  const token = getToken();

  const [release, setRelease] = useState<PackageRelease | null>(null);
  const [preview, setPreview] = useState<PluginPreview | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setTreeLoading(true);
      setError(null);
      try {
        const versions = await listPackageVersions(pluginId, token);
        if (!versions.length) {
          throw new RegistryHttpError(404, "not_found", "plugin not found");
        }
        const latest = [...versions].sort(
          (a, b) => (b.created_at ?? 0) - (a.created_at ?? 0),
        )[0];
        if (cancelled) return;

        let meta: PackageRelease = latest;
        try {
          meta = await getPackageByDigest(
            pluginId,
            latest.package_digest,
            token,
          );
        } catch {
          /* list meta is enough for non-preview fields */
        }
        if (cancelled) return;

        if (meta.package_kind && meta.package_kind !== "plugin") {
          throw new RegistryHttpError(
            404,
            "not_found",
            "not a plugin package (use Datasets for databases)",
          );
        }

        setRelease(meta);
        setPreview(meta.plugin_preview || null);

        const files = await listPackageFiles(
          pluginId,
          latest.package_digest,
          token,
        );
        if (cancelled) return;
        const nested = buildNestedTree(files.items);
        setTree(nested);
        setFilePaths(
          files.items.filter((e) => e.type !== "dir").map((e) => e.path),
        );
        const prefer =
          files.items.find((e) => e.path === "plugin.yaml") ||
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
  }, [pluginId, token]);

  useEffect(() => {
    if (!release || !selectedPath) {
      setFileContent(null);
      setFileNote(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    setFileNote(null);
    getPackageFile(pluginId, release.package_digest, selectedPath, token)
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
  }, [pluginId, release, selectedPath, token]);

  const installCmd = useMemo(() => {
    if (!release) return `bora plugin install ${pluginId}@<version>`;
    return `bora plugin install ${pluginId}@${release.version}`;
  }, [pluginId, release]);

  const formatBadge =
    preview?.format ||
    (release?.package_kind === "plugin" ? "bora.plugin/1" : null);

  const declared = useMemo(() => declaredSlotsFromPreview(preview), [preview]);
  const previewFiles = filePaths.length ? filePaths : preview?.files || [];

  function openSlotPath(path: string) {
    setSelectedPath(path);
    const el = document.getElementById("plugin-files");
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Plugin marketplace", href: "/plugins" },
          { label: pluginId || "…" },
        ]}
        className="mb-4"
      />

      <div className="mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
            {pluginId}
          </h1>
          {formatBadge ? (
            <span className="text-[11px] font-medium font-mono px-2 py-0.5 rounded border border-hairline bg-canvas-soft text-body">
              {formatBadge}
            </span>
          ) : (
            <span className="text-[11px] font-medium uppercase tracking-wide px-2 py-0.5 rounded border border-hairline bg-canvas-soft text-mute">
              plugin
            </span>
          )}
          {release?.official ? (
            <span className="text-[11px] font-medium uppercase tracking-wide px-2 py-0.5 rounded border border-hairline bg-canvas-soft text-ink">
              official
            </span>
          ) : null}
        </div>
        {release ? (
          <p className="text-sm text-mute mt-1">
            v{release.version} · {release.visibility}
            {release.org_id ? (
              <>
                {" "}
                · org{" "}
                <Link
                  to={`/organizations/${encodeURIComponent(release.org_id)}`}
                  className="font-mono text-xs text-body hover:text-ink"
                >
                  {release.org_id}
                </Link>
              </>
            ) : null}{" "}
            ·{" "}
            <span className="font-mono text-xs">
              {release.package_digest.slice(0, 19)}…
            </span>
          </p>
        ) : null}
      </div>

      {loading && <p className="text-sm text-mute">Loading…</p>}
      {error && (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm">
          <p className="text-error font-medium">Could not load plugin</p>
          <p className="mt-1 font-mono text-xs text-body">{error}</p>
          <p className="mt-3">
            <Link to="/plugins" className="underline underline-offset-2 text-body">
              ← Back to marketplace
            </Link>
          </p>
        </div>
      )}

      {!loading && !error && release && (
        <div className="space-y-6">
          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Install (CLI)</h2>
            <CommandStrip command={installCmd} />
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Declared slots</h2>
            <PluginSlotTimeline
              declared={declared}
              files={previewFiles}
              onOpenPath={openSlotPath}
            />
          </section>

          <section id="plugin-files" className="space-y-2">
            <h2 className="text-sm font-medium text-ink">Files</h2>
            <p className="text-xs text-mute">
              Read-only preview. The browser never executes plugin code.
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
    </Shell>
  );
}
