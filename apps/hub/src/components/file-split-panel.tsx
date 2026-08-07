import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FilePreview } from "@/components/file-preview";
import { FileTypeIcon } from "@/components/file-type-icon";
import { Input } from "@/components/ui/input";
import { countFiles } from "@/lib/file-icons";
import type { TreeNode } from "@/lib/file-tree";
import { cn } from "@/lib/utils";

function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  const q = query.trim().toLowerCase();
  if (!q) return nodes;
  const out: TreeNode[] = [];
  for (const node of nodes) {
    if (node.type === "file") {
      if (node.name.toLowerCase().includes(q) || node.path.toLowerCase().includes(q)) {
        out.push(node);
      }
      continue;
    }
    const kids = node.children ? filterTree(node.children, q) : [];
    if (kids.length > 0 || node.name.toLowerCase().includes(q)) {
      out.push({
        ...node,
        children: kids.length > 0 ? kids : node.children,
      });
    }
  }
  return out;
}

function TreeBranch({
  nodes,
  depth,
  selectedPath,
  onSelect,
  openDirs,
  toggleDir,
}: {
  nodes: TreeNode[];
  depth: number;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  openDirs: Set<string>;
  toggleDir: (path: string) => void;
}) {
  return (
    <ul className={cn(depth === 0 && "pb-2")}>
      {nodes.map((node) => {
        if (node.type === "dir") {
          const open = openDirs.has(node.path);
          return (
            <li key={`d:${node.path}`}>
              <button
                type="button"
                onClick={() => toggleDir(node.path)}
                className={cn(
                  "w-full flex items-center gap-1 text-left h-7 pr-2 text-[12.5px]",
                  "text-body hover:bg-row-hover transition-colors rounded-[4px]",
                )}
                style={{ paddingLeft: 8 + depth * 12 }}
                title={node.path}
              >
                {open ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-mute" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-mute" />
                )}
                <FileTypeIcon name={node.name} kind="dir" expanded={open} />
                <span className="truncate font-medium">{node.name}</span>
              </button>
              {open && node.children && node.children.length > 0 ? (
                <TreeBranch
                  nodes={node.children}
                  depth={depth + 1}
                  selectedPath={selectedPath}
                  onSelect={onSelect}
                  openDirs={openDirs}
                  toggleDir={toggleDir}
                />
              ) : null}
            </li>
          );
        }
        const selected = selectedPath === node.path;
        return (
          <li key={`f:${node.path}`}>
            <button
              type="button"
              onClick={() => onSelect(node.path)}
              className={cn(
                "w-full flex items-center gap-1.5 text-left h-7 pr-2 text-[12.5px] truncate transition-colors rounded-[4px]",
                selected
                  ? "bg-canvas text-ink font-medium shadow-[inset_0_0_0_1px_var(--color-hairline)]"
                  : "text-body hover:bg-row-hover",
              )}
              style={{ paddingLeft: 8 + depth * 12 + 18 }}
              title={node.path}
            >
              <FileTypeIcon name={node.name} kind="file" />
              <span className="truncate">{node.name}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function allDirPaths(nodes: TreeNode[], acc: string[] = []): string[] {
  for (const n of nodes) {
    if (n.type === "dir") {
      acc.push(n.path);
      if (n.children) allDirPaths(n.children, acc);
    }
  }
  return acc;
}

function displayPath(fullPath: string, rootPrefix?: string): string {
  const prefix = (rootPrefix || "").replace(/\/$/, "");
  if (prefix && fullPath.startsWith(prefix + "/")) {
    return fullPath.slice(prefix.length + 1);
  }
  return fullPath;
}

/**
 * Left nested tree + right code preview (Hub package files).
 * Material Icon Theme icons by extension; strip task prefix for display.
 */
export function FileSplitPanel({
  tree,
  treeLoading,
  selectedPath,
  onSelect,
  fileContent,
  fileLoading,
  fileNote,
  rootPrefix,
}: {
  tree: TreeNode[];
  treeLoading: boolean;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  fileContent: string | null;
  fileLoading: boolean;
  fileNote: string | null;
  rootPrefix?: string;
}) {
  const treeKey = useMemo(() => tree.map((n) => n.path).join("|"), [tree]);
  const [openDirs, setOpenDirs] = useState<Set<string>>(() => new Set());
  const [query, setQuery] = useState("");

  useEffect(() => {
    setOpenDirs(new Set(allDirPaths(tree)));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- treeKey is the intentional dep
  }, [treeKey]);

  const fileCount = useMemo(() => countFiles(tree), [tree]);
  const visibleTree = useMemo(() => filterTree(tree, query), [tree, query]);

  // When searching, expand all dirs in the filtered tree
  useEffect(() => {
    if (query.trim()) {
      setOpenDirs(new Set(allDirPaths(visibleTree)));
    }
  }, [query, visibleTree]);

  function toggleDir(path: string) {
    setOpenDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <div
      className={cn(
        "grid grid-cols-1 md:grid-cols-[280px_1fr] gap-0",
        "rounded-[8px] border border-hairline overflow-hidden",
        "min-h-[360px] md:min-h-[480px]",
      )}
    >
      <aside
        className={cn(
          "border-b md:border-b-0 md:border-r border-hairline bg-canvas-soft",
          "min-h-[200px] md:min-h-[480px] max-h-[50vh] md:max-h-[75vh]",
          "flex flex-col",
        )}
      >
        <div className="flex items-center justify-between px-3 py-2 border-b border-hairline shrink-0">
          <span className="text-[11px] font-medium uppercase tracking-wide text-mute">
            Files
          </span>
          <span className="text-[11px] tabular-nums text-mute">
            {fileCount} file{fileCount === 1 ? "" : "s"}
          </span>
        </div>
        <div className="px-2 py-2 border-b border-hairline shrink-0">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-mute" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="h-8 pl-7 text-xs bg-canvas"
              aria-label="Search files"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-1 pt-1">
          {treeLoading ? (
            <p className="text-xs text-mute p-3">Loading tree…</p>
          ) : visibleTree.length === 0 ? (
            <p className="text-xs text-mute p-3">
              {query.trim() ? "No matches." : "No files in this scope."}
            </p>
          ) : (
            <TreeBranch
              nodes={visibleTree}
              depth={0}
              selectedPath={selectedPath}
              onSelect={onSelect}
              openDirs={openDirs}
              toggleDir={toggleDir}
            />
          )}
        </div>
      </aside>
      <div
        className={cn(
          "flex flex-col min-h-[200px] md:min-h-[480px]",
          "max-h-[75vh] overflow-hidden",
        )}
      >
        {selectedPath ? (
          <div className="px-3 py-2 border-b border-hairline text-[12px] font-mono text-mute shrink-0 bg-canvas-soft flex items-center gap-2">
            <FileTypeIcon
              name={selectedPath.split("/").pop() || selectedPath}
              kind="file"
            />
            <span className="truncate text-ink">
              {displayPath(selectedPath, rootPrefix)}
            </span>
          </div>
        ) : null}
        <div className="p-0 flex-1 min-h-0 overflow-auto">
          {fileLoading ? (
            <p className="text-sm text-mute p-3">Loading file…</p>
          ) : fileContent != null ? (
            <FilePreview
              path={selectedPath}
              content={fileContent}
              note={fileNote}
            />
          ) : (
            <p className="text-sm text-mute p-3">Select a file to preview.</p>
          )}
        </div>
      </div>
    </div>
  );
}
