import { useEffect, useMemo, useState } from "react";

import { FileSplitPanel } from "@/components/file-split-panel";
import {
  decodeFileContent,
  getPackageFile,
  listPackageFiles,
  RegistryHttpError,
  type FileItem,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { buildNestedTree, pathMatchesPrefixes } from "@/lib/file-tree";

/** Package-file preview limited to a binding's declared ``overlays:`` prefixes. */
export function OverlayFilePanel({
  databaseId,
  packageDigest,
  prefixes,
}: {
  databaseId: string;
  packageDigest: string;
  prefixes: string[];
}) {
  const token = getToken();
  const overlayKey = prefixes.join("\n");
  const prefixList = useMemo(
    () => overlayKey.split("\n").filter(Boolean),
    [overlayKey],
  );
  const [fileItems, setFileItems] = useState<FileItem[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileNote, setFileNote] = useState<string | null>(null);

  const canPreview = Boolean(databaseId && packageDigest && overlayKey);

  useEffect(() => {
    if (!canPreview) {
      setFileItems([]);
      setSelectedPath(null);
      setFileContent(null);
      setFileNote(null);
      setTreeLoading(false);
      return;
    }
    let cancelled = false;
    setTreeLoading(true);
    setFileNote(null);
    listPackageFiles(databaseId, packageDigest, token)
      .then((files) => {
        if (cancelled) return;
        const matched = files.items.filter(
          (item) => item.type !== "dir" && pathMatchesPrefixes(item.path, prefixList),
        );
        setFileItems(matched);
        const prefer =
          prefixList
            .map((prefix) =>
              matched.find(
                (item) => item.path === prefix || item.path.startsWith(`${prefix}/`),
              ),
            )
            .find(Boolean) || matched[0];
        setSelectedPath(prefer?.path ?? null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setFileItems([]);
        setSelectedPath(null);
        if (err instanceof RegistryHttpError) {
          setFileNote(`${err.code}: ${err.message}`);
        } else {
          setFileNote(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setTreeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canPreview, databaseId, overlayKey, packageDigest, prefixList, token]);

  const tree = useMemo(
    () => (canPreview ? buildNestedTree(fileItems, "overlays") : []),
    [canPreview, fileItems],
  );

  useEffect(() => {
    if (!canPreview || !selectedPath) {
      setFileContent(null);
      return;
    }
    let cancelled = false;
    setFileLoading(true);
    getPackageFile(databaseId, packageDigest, selectedPath, token)
      .then((file) => {
        if (cancelled) return;
        try {
          setFileContent(decodeFileContent(file));
          setFileNote(null);
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
  }, [canPreview, databaseId, packageDigest, selectedPath, token]);

  if (!canPreview) return null;

  return (
    <div className="rounded-[8px] border border-hairline overflow-hidden">
      <FileSplitPanel
        tree={tree}
        treeLoading={treeLoading}
        selectedPath={selectedPath}
        onSelect={setSelectedPath}
        fileContent={fileContent}
        fileLoading={fileLoading}
        fileNote={fileNote}
        rootPrefix="overlays"
      />
    </div>
  );
}
