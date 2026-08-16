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
import { decodeDatasetId, listSuites } from "@/lib/api";
import { getToken } from "@/lib/auth";

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
  const [slotPrevious, setSlotPrevious] = useState<
    Array<{ run_id?: string | null; status?: string | null }>
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
      .then((suites) => {
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
          setSlotCurrentRunId(hit.run_id ?? null);
          setSlotPrevious(prev);
          return;
        }
        setSlotCurrentRunId(null);
        setSlotPrevious([]);
      })
      .catch(() => {
        if (!cancelled) {
          setSlotCurrentRunId(null);
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
