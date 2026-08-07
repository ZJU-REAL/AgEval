import { useMemo } from "react";

import type { TreeEntry } from "@/lib/api";
import { CodeHighlight } from "@/lib/code-highlight";
import { cn } from "@/lib/utils";

import { actorLabel, type ActorRow } from "./types";

export function FileSplitPanel({
  tree,
  treeLoading,
  selectedPath,
  onSelect,
  fileContent,
  fileLoading,
  fileNote,
  groupByProfile = false,
  actors = [],
  apiGroups = null,
}: {
  tree: TreeEntry[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
  groupByProfile?: boolean;
  actors?: ActorRow[];
  apiGroups?: Array<{
    key: string;
    profile_id?: string | null;
    label?: string;
  }> | null;
}) {
  // Virtual profile folders for multi-role Agent tab (real paths preserved).
  const groupedTree = useMemo(() => {
    if (!groupByProfile || tree.length === 0) return null;
    const profileKeys = new Set(
      tree.map((e) => e.profile_id).filter((p): p is string => !!p),
    );
    if (profileKeys.size < 2) return null;

    const actorByPid = new Map(
      actors.map((a) => [a.profile_id || "", a] as const),
    );
    const order: string[] = [];
    if (apiGroups && apiGroups.length > 0) {
      for (const g of apiGroups) {
        if (g.key && !order.includes(g.key)) order.push(g.key);
      }
    }
    for (const e of tree) {
      const key = e.profile_id || "__ungrouped__";
      if (!order.includes(key)) order.push(key);
    }

    const byKey = new Map<string, TreeEntry[]>();
    for (const e of tree) {
      const key = e.profile_id || "__ungrouped__";
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key)!.push(e);
    }

    const labels = new Map<string, string>();
    for (const key of order) {
      if (key === "__ungrouped__") {
        labels.set(key, "other");
        continue;
      }
      const actor = actorByPid.get(key);
      labels.set(key, actor ? actorLabel(actor, key) : key);
    }
    return { order, byKey, labels };
  }, [tree, groupByProfile, actors, apiGroups]);

  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-[240px_1fr] gap-0",
        "rounded-[8px] border border-hairline overflow-hidden",
        /* Keep a stable pane even with 1-file trees (e.g. Lock) */
        "min-h-[360px] md:min-h-[420px]",
      )}
    >
      <aside
        className={cn(
          "border-b md:border-b-0 md:border-r border-hairline bg-canvas-soft",
          "min-h-[160px] md:min-h-[420px] max-h-[50vh] md:max-h-[70vh]",
          "overflow-y-auto",
        )}
      >
        {treeLoading ? (
          <p className="text-xs text-mute p-3">Loading tree…</p>
        ) : tree.length === 0 ? (
          <p className="text-xs text-mute p-3">No files in this scope.</p>
        ) : groupedTree ? (
          <div className="py-1 min-h-[140px] md:min-h-[380px]">
            {groupedTree.order.map((key) => (
              <div key={key} className="mb-1">
                <div
                  className="px-3 py-1 text-[11px] font-mono text-mute sticky top-0 bg-canvas-soft border-b border-hairline/60 truncate"
                  title={groupedTree.labels.get(key)}
                >
                  {groupedTree.labels.get(key)}
                </div>
                <ul>
                  {(groupedTree.byKey.get(key) || []).map((e) => (
                    <li key={e.path}>
                      <button
                        type="button"
                        onClick={() => onSelect(e.path)}
                        className={cn(
                          "w-full text-left px-3 py-1.5 text-[12px] font-mono truncate transition-colors",
                          selectedPath === e.path
                            ? "bg-canvas text-ink font-medium"
                            : "text-body hover:bg-canvas/80",
                        )}
                        title={e.path}
                      >
                        {e.invocation ? `${e.invocation}/${e.name}` : e.path}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ) : (
          <ul className="py-1 min-h-[140px] md:min-h-[380px]">
            {tree.map((e) => (
              <li key={e.path}>
                <button
                  type="button"
                  onClick={() => onSelect(e.path)}
                  className={cn(
                    "w-full text-left px-3 py-1.5 text-[12px] font-mono truncate transition-colors",
                    selectedPath === e.path
                      ? "bg-canvas text-ink font-medium"
                      : "text-body hover:bg-row-hover",
                  )}
                  title={e.path}
                >
                  {e.path}
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>
      <div
        className={cn(
          "flex flex-col min-h-[200px] md:min-h-[420px]",
          "max-h-[70vh] overflow-hidden",
        )}
      >
        {selectedPath ? (
          <div className="px-3 py-1.5 border-b border-hairline text-[11px] font-mono text-mute shrink-0 bg-canvas-soft">
            {selectedPath}
          </div>
        ) : null}
        <div className="p-0 flex-1 min-h-0 overflow-auto">
          {fileLoading ? (
            <p className="text-sm text-mute p-3">Loading file…</p>
          ) : (
            <>
              {fileNote ? (
                <p className="text-xs text-mute px-3 pt-2">{fileNote}</p>
              ) : null}
              {fileContent != null ? (
                <pre
                  className={cn(
                    "m-0 p-3 min-h-full overflow-auto",
                    "whitespace-pre-wrap break-words font-mono text-[12px] leading-5",
                    "bg-code-bg text-shell-plain",
                  )}
                >
                  <code className="font-mono">
                    <CodeHighlight path={selectedPath} content={fileContent} />
                  </code>
                </pre>
              ) : (
                <p className="text-sm text-mute p-3">Select a file to preview.</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
