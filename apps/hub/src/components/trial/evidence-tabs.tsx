import { UnderlineTabs } from "@/components/underline-tabs";
import type { TrajectoryStep, TreeEntry, Trial } from "@/lib/trial-types";

import { FileSplitPanel } from "./file-split-panel";
import { TAB_LABELS, type TabId } from "./tabs";
import { TrajectoryPanel } from "./trajectory-panel";

export function EvidenceTabs({
  availableTabs,
  activeTab,
  onTabChange,
  trajLoading,
  steps,
  trajNote,
  result,
  actors,
  tree,
  treeLoading,
  selectedPath,
  onSelectPath,
  fileContent,
  fileLoading,
  fileNote,
  treeGroups,
}: {
  availableTabs: TabId[];
  activeTab: TabId | null;
  onTabChange: (tab: TabId) => void;
  trajLoading: boolean;
  steps: TrajectoryStep[];
  trajNote: string | null;
  result: Record<string, unknown> | null;
  actors: NonNullable<Trial["actors"]>;
  tree: TreeEntry[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelectPath: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
  treeGroups: Array<{
    key: string;
    profile_id?: string | null;
    label?: string;
  }> | null;
}) {
  if (availableTabs.length === 0) {
    return (
      <p className="text-sm text-mute">
        No evidence tabs for this uploaded Attempt archive.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {activeTab ? (
        <UnderlineTabs
          ariaLabel="Evidence tabs"
          value={activeTab}
          onChange={onTabChange}
          items={availableTabs.map((tab) => ({
            id: tab,
            label: TAB_LABELS[tab],
          }))}
        />
      ) : null}

      {activeTab === "trajectory" && (
        <TrajectoryPanel
          loading={trajLoading}
          steps={steps}
          note={trajNote}
          result={result}
          actors={actors}
        />
      )}

      {activeTab && activeTab !== "trajectory" && (
        <FileSplitPanel
          tree={tree}
          treeLoading={treeLoading}
          selectedPath={selectedPath}
          onSelect={onSelectPath}
          fileContent={fileContent}
          fileLoading={fileLoading}
          fileNote={fileNote}
          groupByProfile={activeTab === "agent"}
          actors={actors}
          apiGroups={treeGroups}
        />
      )}
    </div>
  );
}
