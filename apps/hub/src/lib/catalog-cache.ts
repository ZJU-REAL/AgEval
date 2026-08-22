import type { PackageRelease } from "@/lib/api";

const LIST_KEY = "ageval-hub.catalog.list";
const PREVIEW_KEY = "ageval-hub.catalog.preview";

type ListStore = Record<string, PackageRelease[]>;
type PreviewStore = Record<string, PackageRelease>;

let lists: ListStore | null = null;
let previews: PreviewStore | null = null;

function readStore<T extends object>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeStore(key: string, value: object): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota / private mode */
  }
}

function listStore(): ListStore {
  if (!lists) lists = readStore<ListStore>(LIST_KEY, {});
  return lists;
}

function previewStore(): PreviewStore {
  if (!previews) previews = readStore<PreviewStore>(PREVIEW_KEY, {});
  return previews;
}

export function catalogListCacheKey(
  kind: "plugin" | "agent",
  scope: string,
  signedIn: boolean,
): string {
  return `${kind}:${scope}:${signedIn ? "1" : "0"}`;
}

export function catalogPreviewKey(row: Pick<PackageRelease, "dataset_id" | "package_digest">): string {
  return `${row.dataset_id}@${row.package_digest}`;
}

export function readCatalogList(key: string): PackageRelease[] | null {
  const hit = listStore()[key];
  return hit ? hit.map(hydrateCatalogRow) : null;
}

export function writeCatalogList(key: string, rows: PackageRelease[]): void {
  const store = listStore();
  store[key] = rows;
  writeStore(LIST_KEY, store);
  const preview = previewStore();
  let dirty = false;
  for (const row of rows) {
    if (!row.plugin_preview && !row.agent_preview) continue;
    preview[catalogPreviewKey(row)] = row;
    dirty = true;
  }
  if (dirty) writeStore(PREVIEW_KEY, preview);
}

export function readCatalogPreview(key: string): PackageRelease | undefined {
  return previewStore()[key];
}

export function writeCatalogPreview(row: PackageRelease): void {
  const store = previewStore();
  store[catalogPreviewKey(row)] = row;
  writeStore(PREVIEW_KEY, store);
}

export function hydrateCatalogRow(row: PackageRelease): PackageRelease {
  if (row.plugin_preview || row.agent_preview) return row;
  const extra = readCatalogPreview(catalogPreviewKey(row));
  if (!extra) return row;
  return {
    ...extra,
    download_count: row.download_count,
    favorite_count: row.favorite_count,
    favorited: row.favorited,
  };
}
