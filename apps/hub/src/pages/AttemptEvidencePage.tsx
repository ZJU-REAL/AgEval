import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { ActorsTable } from "@/components/trial/actors-table";
import { EvidenceTabs } from "@/components/trial/evidence-tabs";
import { OutcomeStrip } from "@/components/trial/outcome-strip";
import { PhaseTimingBar } from "@/components/trial/phase-timing-bar";
import { TrialHeader } from "@/components/trial/trial-header";
import { useAttemptEvidence } from "@/hooks/use-attempt-evidence";
import {
  decodeDatasetId,
  decodeFileContent,
  getAttemptFile,
  listSuites,
} from "@/lib/api";
import { toArchivePath } from "@/lib/attempt-evidence";
import { getToken } from "@/lib/auth";

async function readAttemptStartedAt(
  runId: string,
  token: string | null,
): Promise<string | null> {
  for (const rel of ["summary.json", "result.json"]) {
    try {
      const file = await getAttemptFile(runId, toArchivePath(rel, runId), token);
      const text = decodeFileContent(file);
      if (!text) continue;
      const data = JSON.parse(text) as {
        started_at?: unknown;
        started?: unknown;
        phase_timing?: { started_at?: unknown };
      };
      for (const raw of [
        data.started_at,
        data.started,
        data.phase_timing?.started_at,
      ]) {
        if (typeof raw === "string" && raw.trim()) return raw.trim();
      }
    } catch {
      continue;
    }
  }
  return null;
}

/**
 * Hub Jobs deep-link: uploaded Attempt evidence with viewer-parity IA
 * (outcome, actors, Trajectory / Agent / Verifier / Lock / Runtime tabs).
 *
 * Package Dataset ``shared/`` is browsed on Task Files / Dataset Shared tab —
 * not inside Attempt evidence (Local | Shared does not apply here).
 */
export function AttemptEvidencePage() {
  const { datasetId: rawId, taskId: rawTask, runId: rawRun } = useParams();
  const datasetId = decodeDatasetId(rawId || "");
  const taskId = decodeURIComponent(rawTask || "");
  const runId = decodeURIComponent(rawRun || "");
  const token = getToken();
  const navigate = useNavigate();
  const [slotCurrentRunId, setSlotCurrentRunId] = useState<string | null>(null);
  const [slotCurrentStartedAt, setSlotCurrentStartedAt] = useState<string | null>(
    null,
  );
  const [slotPrevious, setSlotPrevious] = useState<
    Array<{
      run_id?: string | null;
      status?: string | null;
      started_at?: string | null;
      replaced_at?: string | null;
    }>
  >([]);

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

  useEffect(() => {
    let cancelled = false;
    if (!datasetId || !taskId || !runId) return;
    listSuites(datasetId, token)
      .then(async (suites) => {
        if (cancelled) return;
        for (const suite of suites) {
          const hit = (suite.task_refs || []).find((ref) => ref.task_id === taskId);
          if (!hit) continue;
          const prev = hit.previous || [];
          const ids = [
            hit.run_id,
            ...(hit.attempt_run_ids || []),
            ...prev.map((item) => item.run_id),
          ];
          if (!ids.includes(runId)) continue;
          const current = hit.run_id ?? null;
          const [currentAt, ...prevTimes] = await Promise.all([
            current ? readAttemptStartedAt(current, token) : Promise.resolve(null),
            ...prev.map((item) =>
              item.run_id
                ? item.started_at || readAttemptStartedAt(item.run_id, token)
                : Promise.resolve(null),
            ),
          ]);
          if (cancelled) return;
          setSlotCurrentRunId(current);
          setSlotCurrentStartedAt(currentAt);
          setSlotPrevious(
            prev.map((item, i) => ({
              ...item,
              started_at: item.started_at || prevTimes[i] || null,
            })),
          );
          return;
        }
        setSlotCurrentRunId(null);
        setSlotCurrentStartedAt(null);
        setSlotPrevious([]);
      })
      .catch(() => {
        if (!cancelled) {
          setSlotCurrentRunId(null);
          setSlotCurrentStartedAt(null);
          setSlotPrevious([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId, taskId, runId, token]);

  const jobsHref = `/datasets/${encodeURIComponent(datasetId)}/tasks/${encodeURIComponent(taskId)}?tab=jobs`;
  const attemptHref = (id: string) =>
    `/datasets/${encodeURIComponent(datasetId)}/tasks/${encodeURIComponent(taskId)}/attempts/${encodeURIComponent(id)}`;

  return (
    <>
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

        <TrialHeader
          runId={runId}
          taskId={taskId}
          trial={trial}
          slotCurrentRunId={slotCurrentRunId}
          slotCurrentStartedAt={slotCurrentStartedAt}
          slotPrevious={slotPrevious}
          onSlotSelect={(id) => navigate(attemptHref(id))}
        />

        {runCommand ? <CommandStrip command={runCommand} /> : null}

        {loading && <p className="text-sm text-mute">Loading attempt evidence…</p>}

        {error ? (
          <div className="rounded-[8px] border border-hairline bg-canvas-soft p-6 space-y-3">
            <p className="text-sm text-error font-mono">{error}</p>
            <p className="text-sm text-mute">
              Full evidence may not be uploaded yet. Upload with{" "}
              <code className="font-mono">ageval results upload</code> or{" "}
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
              command={`ageval results upload <dataset-root> --run ${runId}`}
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
          </>
        ) : null}

        {!loading && !error && !trial ? (
          <p className="text-sm text-mute">No trial meta for this run.</p>
        ) : null}
      </div>
    </>
  );
}
