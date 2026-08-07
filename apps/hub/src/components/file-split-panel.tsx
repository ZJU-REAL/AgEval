import type { TreeEntry } from "@/lib/api";
import { CodeHighlight } from "@/lib/code-highlight";
import { cn } from "@/lib/utils";

/** Left tree + right preview (Hub package files; no trial-only grouping). */
export function FileSplitPanel({
  tree,
  treeLoading,
  selectedPath,
  onSelect,
  fileContent,
  fileLoading,
  fileNote,
}: {
  tree: TreeEntry[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-[240px_1fr] gap-0",
        "rounded-[8px] border border-hairline overflow-hidden",
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
