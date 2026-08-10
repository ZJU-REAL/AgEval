import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { FileSplitPanel } from "@/components/file-split-panel";
import { Shell } from "@/components/layout";
import {
  decodeDatasetId,
  decodeFileContent,
  getAttempt,
  getAttemptFile,
  listAttemptFiles,
  type AttemptMeta,
  RegistryHttpError,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, type TreeNode } from "@/lib/file-tree";

/**
 * Read-only browse of an uploaded Attempt evidence archive (#43).
 * Reuses package-style file tree + preview; no local bora view IA copy.
 */
export function AttemptEvidencePage() {
  const { datasetId: rawId, taskId: rawTask, runId: rawRun } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const taskId = decodeURIComponent(rawTask || "");
  const runId = decodeURIComponent(rawRun || "");
  const token = getToken();

  const [meta, setMeta] = useState<AttemptMeta | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileNote, setFileNote] = useState<string | null>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [fileLoading, setFileLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rootPrefix = useMemo(() => {
    // Archives pack as .bora/runs/<run_id>/… — prefer that as tree root when present.
    return `.bora/runs/${runId}`;
  }, [runId]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setTreeLoading(true);
      setError(null);
      setMeta(null);
      setTree([]);
      setSelectedPath(null);
      try {
        const m = await getAttempt(runId, token);
        if (cancelled) return;
        setMeta(m);
        const files = await listAttemptFiles(runId, token);
        if (cancelled) return;
        const items = files.items || [];
        // Prefer nested under .bora/runs/<id>; fall back to full archive tree.
        const under = items.filter(
          (e) =>
            e.path === rootPrefix || e.path.startsWith(rootPrefix + "/"),
        );
        const nested = buildNestedTree(
          under.length > 0 ? under : items,
          under.length > 0 ? rootPrefix : undefined,
        );
        setTree(nested);
        const prefer =
          items.find((e) => e.path === `${rootPrefix}/result.json`) ||
          items.find((e) => e.path.endsWith("/result.json") && e.type !== "dir") ||
          items.find((e) => e.path.endsWith("/trajectory.jsonl") && e.type !== "dir") ||
          items.find((e) => e.type !== "dir");
        if (prefer) setSelectedPath(prefer.path);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setTreeLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [runId, token, rootPrefix]);

  useEffect(() => {
    if (!selectedPath) {
      setFileContent(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    setFileNote(null);
    getAttemptFile(runId, selectedPath, token)
      .then((f) => {
        if (cancelled) return;
        setFileContent(decodeFileContent(f));
        if (f.truncated) setFileNote("truncated");
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
  }, [runId, selectedPath, token]);

  const taskHref = `/datasets/${encodeURIComponent(datasetId)}/tasks/${encodeURIComponent(taskId)}?tab=jobs`;

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Datasets", href: "/datasets" },
          {
            label: datasetId,
            href: `/datasets/${encodeURIComponent(datasetId)}`,
          },
          { label: taskId, href: taskHref },
          { label: runId },
        ]}
        className="mb-4"
      />
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
          {runId}
        </h1>
        <p className="text-sm text-mute mt-1">
          Attempt evidence
          {meta?.status ? (
            <>
              {" "}
              · <span className="text-body">{meta.status}</span>
            </>
          ) : null}
          {meta?.uploaded_by ? (
            <>
              {" "}
              · by <span className="font-mono">@{meta.uploaded_by}</span>
            </>
          ) : null}
        </p>
      </div>

      {error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
          <p className="text-sm text-error font-mono">{error}</p>
          <p className="text-sm text-mute">
            Full evidence may not be uploaded yet. Upload with{" "}
            <code className="font-mono">bora results upload</code> or{" "}
            <code className="font-mono">upload-suite --with-attempts</code>, then
            return from{" "}
            <Link to={taskHref} className="text-ink underline-offset-2 hover:underline">
              Jobs
            </Link>
            .
          </p>
          <CommandStrip
            command={`bora results upload <database-root> --run ${runId}`}
          />
        </div>
      ) : (
        <FileSplitPanel
          tree={tree}
          treeLoading={treeLoading}
          selectedPath={selectedPath}
          onSelect={setSelectedPath}
          fileContent={fileContent}
          fileLoading={fileLoading}
          fileNote={fileNote}
          rootPrefix={rootPrefix}
        />
      )}
    </Shell>
  );
}
