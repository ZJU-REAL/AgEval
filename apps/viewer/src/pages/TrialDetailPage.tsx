import { Link, useNavigate, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { CommandStrip } from "@/components/command-strip";
import { Shell } from "@/components/layout";
import { ActorsTable } from "@/components/trial/actors-table";
import { EvidenceTabs } from "@/components/trial/evidence-tabs";
import { OutcomeStrip } from "@/components/trial/outcome-strip";
import { TrialHeader } from "@/components/trial/trial-header";
import { useTrialDetail } from "@/hooks/use-trial-detail";

export function TrialDetailPage() {
  const { jobId = "", taskId = "", runId = "" } = useParams();
  const navigate = useNavigate();
  const detail = useTrialDetail(jobId, taskId, runId);

  function goSibling(id: string | null) {
    if (!id) return;
    navigate(
      `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}/trials/${encodeURIComponent(id)}`,
    );
  }

  const {
    trial,
    result,
    runCommand,
    prevId,
    nextId,
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
  } = detail;

  return (
    <Shell>
      <div className="space-y-5">
        <BreadcrumbNav
          items={[
            { label: "Jobs", href: "/" },
            { label: jobId, href: `/jobs/${encodeURIComponent(jobId)}` },
            {
              label: taskId,
              href: `/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}`,
            },
            { label: runId, href: null },
          ]}
        />

        <TrialHeader
          runId={runId}
          taskId={taskId}
          trial={trial}
          prevId={prevId}
          nextId={nextId}
          onSibling={goSibling}
        />

        {runCommand ? <CommandStrip command={runCommand} /> : null}

        {loading && <p className="text-sm text-mute">Loading trial…</p>}
        {error && <p className="text-sm text-error">{error}</p>}

        {!loading && !error && trial && (
          <>
            <OutcomeStrip trial={trial} />

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

            <p className="text-xs text-mute">
              <Link
                to={`/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}`}
                className="text-link hover:text-link-deep"
              >
                ← Back to trials
              </Link>
            </p>
          </>
        )}
      </div>
    </Shell>
  );
}
