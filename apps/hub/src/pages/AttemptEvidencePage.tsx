import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { Shell } from "@/components/layout";
import { ActorsTable } from "@/components/trial/actors-table";
import { EvidenceTabs } from "@/components/trial/evidence-tabs";
import { OutcomeStrip } from "@/components/trial/outcome-strip";
import { PhaseTimingBar } from "@/components/trial/phase-timing-bar";
import { TrialHeader } from "@/components/trial/trial-header";
import { useAttemptEvidence } from "@/hooks/use-attempt-evidence";
import {
  decodeDatasetId,
  decodeFileContent,
  getPackageFile,
  hasSharedFiles,
  listPackageFiles,
  listPackageVersions,
  RegistryHttpError,
  type FileItem,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree } from "@/lib/file-tree";
import { cn } from "@/lib/utils";

type FilesScope = "local" | "shared";

/**
 * Hub Jobs deep-link: uploaded Attempt evidence with viewer-parity IA
 * (outcome, actors, Trajectory / Agent / Verifier / Lock / Runtime tabs).
 */
export function AttemptEvidencePage() {
  const { datasetId: rawId, taskId: rawTask, runId: rawRun } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const taskId = decodeURIComponent(rawTask || "");
  const runId = decodeURIComponent(rawRun || "");
  const token = getToken();

  const {
    trial,
    result,
    runCommand,
    error,
    loading,
    activeTab,
    setActiveTab,
    availableTabs,
    steps,
    trajNote,
    trajLoading,
    tree,
    treeGroups,
    treeLoading,
    selectedPath,
    setSelectedPath,
    fileContent,
    fileNote,
    fileLoading,
  } = useAttemptEvidence(runId, taskId, token);

  const jobsHref = `/datasets/${encodeURIComponent(datasetId)}/tasks/${encodeURIComponent(taskId)}?tab=jobs`;

  // #65: Local = attempt evidence; Shared = Dataset package shared/ (read-only).
  const [filesScope, setFilesScope] = useState<FilesScope>("local");
  const [pkgDigest, setPkgDigest] = useState<string | null>(null);
  const [pkgItems, setPkgItems] = useState<FileItem[]>([]);
  const [sharedSelected, setSharedSelected] = useState<string | null>(null);
  const [sharedContent, setSharedContent] = useState<string | null>(null);
  const [sharedNote, setSharedNote] = useState<string | null>(null);
  const [sharedLoading, setSharedLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadPkg() {
      try {
        const versions = await listPackageVersions(datasetId, token);
        if (!versions.length || cancelled) return;
        const latest = [...versions].sort(
          (a, b) => (b.created_at ?? 0) - (a.created_at ?? 0),
        )[0];
        const files = await listPackageFiles(
          datasetId,
          latest.package_digest,
          token,
        );
        if (cancelled) return;
        setPkgDigest(latest.package_digest);
        setPkgItems(files.items);
        if (hasSharedFiles(files.items)) {
          const prefer =
            files.items.find((e) => e.path === "shared/README.md") ||
            files.items.find(
              (e) => e.type !== "dir" && e.path.startsWith("shared/"),
            );
          if (prefer) setSharedSelected(prefer.path);
        }
      } catch {
        if (!cancelled) {
          setPkgDigest(null);
          setPkgItems([]);
        }
      }
    }
    void loadPkg();
    return () => {
      cancelled = true;
    };
  }, [datasetId, token]);

  const sharedPresent = useMemo(() => hasSharedFiles(pkgItems), [pkgItems]);
  const sharedTree = useMemo(
    () => buildNestedTree(pkgItems, "shared"),
    [pkgItems],
  );

  useEffect(() => {
    if (!pkgDigest || !sharedSelected || filesScope !== "shared") {
      setSharedContent(null);
      return;
    }
    let cancelled = false;
    setSharedLoading(true);
    setSharedNote(null);
    getPackageFile(datasetId, pkgDigest, sharedSelected, token)
      .then((f) => {
        if (cancelled) return;
        setSharedContent(decodeFileContent(f));
        if (f.truncated) setSharedNote("truncated");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSharedContent(null);
        if (err instanceof RegistryHttpError) {
          setSharedNote(`${err.code}: ${err.message}`);
        } else {
          setSharedNote(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setSharedLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, pkgDigest, sharedSelected, token, filesScope]);

  return (
    <Shell>
      <div className="space-y-5">
        <BreadcrumbNav
          items={[
            { label: "Datasets", href: "/datasets" },
            {
              label: datasetId,
              href: `/datasets/${encodeURIComponent(datasetId)}`,
            },
            { label: taskId, href: jobsHref },
            { label: runId, href: null },
          ]}
        />

        <TrialHeader runId={runId} taskId={taskId} trial={trial} />

        {runCommand ? <CommandStrip command={runCommand} /> : null}

        {loading && <p className="text-sm text-mute">Loading attempt evidence…</p>}

        {error ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
            <p className="text-sm text-error font-mono">{error}</p>
            <p className="text-sm text-mute">
              Full evidence may not be uploaded yet. Upload with{" "}
              <code className="font-mono">bora results upload</code> or{" "}
              <code className="font-mono">upload-suite --with-attempts</code>,
              then return from{" "}
              <Link
                to={jobsHref}
                className="text-ink underline-offset-2 hover:underline"
              >
                Jobs
              </Link>
              .
            </p>
            <CommandStrip
              command={`bora results upload <database-root> --run ${runId}`}
            />
          </div>
        ) : null}

        {!loading && !error && trial ? (
          <>
            <OutcomeStrip trial={trial} />

            <PhaseTimingBar
              phaseTiming={trial.phase_timing}
              tokenTiming={trial.token_timing}
            />

            {trial.actors && trial.actors.length > 0 ? (
              <ActorsTable actors={trial.actors} />
            ) : null}

            <div className="inline-flex rounded-[8px] border border-hairline p-0.5 bg-canvas-soft">
              {(
                [
                  ["local", "Local"],
                  ["shared", "Shared"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setFilesScope(id)}
                  className={cn(
                    "px-3 py-1.5 text-xs rounded-[6px] transition-colors",
                    filesScope === id
                      ? "bg-canvas text-ink font-medium shadow-sm"
                      : "text-body hover:text-ink",
                  )}
                >
                  {label}
                  {id === "shared" && !sharedPresent ? (
                    <span className="ml-1 text-mute font-normal">(none)</span>
                  ) : null}
                </button>
              ))}
            </div>

            {filesScope === "local" ? (
              <EvidenceTabs
                availableTabs={availableTabs}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                trajLoading={trajLoading}
                steps={steps}
                trajNote={trajNote}
                result={result}
                actors={trial.actors || []}
                tree={tree}
                treeLoading={treeLoading}
                selectedPath={selectedPath}
                onSelectPath={setSelectedPath}
                fileContent={fileContent}
                fileLoading={fileLoading}
                fileNote={fileNote}
                treeGroups={treeGroups}
              />
            ) : !sharedPresent ? (
              <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 text-sm text-mute">
                No <code className="font-mono">shared/</code> in this Dataset
                package. Local tab shows Attempt evidence only.
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-mute">
                  Dataset <code className="font-mono">shared/**</code> (package
                  digest; not Attempt archive). Gold stays under{" "}
                  <code className="font-mono">evaluation/</code>.
                </p>
                <FileSplitPanel
                  tree={sharedTree}
                  treeLoading={false}
                  selectedPath={sharedSelected}
                  onSelect={setSharedSelected}
                  fileContent={sharedContent}
                  fileLoading={sharedLoading}
                  fileNote={sharedNote}
                  rootPrefix="shared"
                />
              </div>
            )}
          </>
        ) : null}

        {!loading && !error && !trial ? (
          <p className="text-sm text-mute">No trial meta for this run.</p>
        ) : null}
      </div>
    </Shell>
  );
}
