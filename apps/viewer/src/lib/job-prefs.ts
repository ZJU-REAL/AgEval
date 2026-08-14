/** Operator chrome for Jobs rows. Browser-local only; not evidence. */

export type JobPref = {
  pinned: boolean;
  note: string;
};

const STORAGE_KEY = "bora-viewer-job-prefs";

type Store = Record<string, Record<string, JobPref>>;

export function emptyJobPref(): JobPref {
  return { pinned: false, note: "" };
}

export function prefsScope(databaseId: string | null | undefined): string {
  const text = (databaseId || "").trim();
  return text || "_";
}

export function hasJobNote(pref: JobPref | undefined): boolean {
  return Boolean(pref?.note.trim());
}

function readStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== "object" || Array.isArray(data)) return {};
    return data as Store;
  } catch {
    return {};
  }
}

function writeStore(store: Store): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    /* quota / private mode */
  }
}

export function loadJobPrefs(databaseId: string): Record<string, JobPref> {
  const scope = prefsScope(databaseId);
  const bucket = readStore()[scope];
  if (!bucket || typeof bucket !== "object") return {};
  const out: Record<string, JobPref> = {};
  for (const [jobId, raw] of Object.entries(bucket)) {
    if (!raw || typeof raw !== "object") continue;
    const pinned = Boolean((raw as JobPref).pinned);
    const note = typeof (raw as JobPref).note === "string" ? (raw as JobPref).note : "";
    if (!pinned && !note.trim()) continue;
    out[jobId] = { pinned, note };
  }
  return out;
}

export function saveJobPrefs(
  databaseId: string,
  prefs: Record<string, JobPref>,
): void {
  const scope = prefsScope(databaseId);
  const store = readStore();
  const bucket: Record<string, JobPref> = {};
  for (const [jobId, pref] of Object.entries(prefs)) {
    if (!pref.pinned && !pref.note.trim()) continue;
    bucket[jobId] = { pinned: pref.pinned, note: pref.note };
  }
  if (Object.keys(bucket).length === 0) {
    delete store[scope];
  } else {
    store[scope] = bucket;
  }
  writeStore(store);
}
