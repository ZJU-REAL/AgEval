/** Registry HTTP client for Hub SPA (#39 / #40). */

export type PackageRelease = {
  database_id: string;
  version: string;
  visibility: string;
  package_digest: string;
  blob_digest: string;
  size: number;
  media_type?: string;
  created_at?: number;
};

export type FileItem = {
  path: string;
  type: "file" | "dir" | string;
  size: number;
};

export type TreeEntry = {
  path: string;
  name: string;
  type?: string;
  size?: number;
};

export type FileContent = {
  path: string;
  size: number;
  encoding: "utf-8" | "base64" | string;
  content: string;
  truncated?: boolean;
};

export type SuiteRow = {
  suite_run_id: string;
  database_id?: string;
  database_version?: string;
  visibility?: string;
  pass_rate?: number | null;
  mean_score?: number | null;
  metrics?: Record<string, unknown>;
  task_refs?: Array<{
    task_id?: string;
    status?: string | null;
    score?: number | null;
    run_id?: string | null;
  }>;
  agent_label?: string;
  model_label?: string;
  config_fingerprint?: string;
  config_homogeneous?: boolean;
  actors_summary?: Array<Record<string, string>>;
  exit_code?: number | null;
  created_at?: number | string;
  note?: string;
};

export class RegistryHttpError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function registryBase(): string {
  const raw = import.meta.env.VITE_REGISTRY_URL as string | undefined;
  if (raw && raw.trim()) return raw.replace(/\/$/, "");
  // Dev: same-origin → Vite proxy to Registry.
  return "";
}

function authHeaders(token: string | null): HeadersInit {
  const h: Record<string, string> = { Accept: "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function requestJson<T>(
  path: string,
  opts: { token?: string | null; method?: string; body?: unknown } = {},
): Promise<T> {
  const url = `${registryBase()}${path}`;
  const res = await fetch(url, {
    method: opts.method || "GET",
    headers: {
      ...authHeaders(opts.token ?? null),
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { message: text };
  }
  if (!res.ok) {
    const obj = data as { error?: string; message?: string };
    throw new RegistryHttpError(
      res.status,
      String(obj.error || "http_error"),
      String(obj.message || res.statusText || "request failed"),
    );
  }
  return data as T;
}

export function encodeDatasetId(id: string): string {
  return encodeURIComponent(id);
}

export function decodeDatasetId(param: string): string {
  return decodeURIComponent(param);
}

export async function listPackages(token: string | null): Promise<PackageRelease[]> {
  // With token, server may include private; without, public only.
  const data = await requestJson<{ items?: PackageRelease[] }>("/v1/packages", {
    token,
  });
  return Array.isArray(data.items) ? data.items : [];
}

export async function listPackageVersions(
  databaseId: string,
  token: string | null,
): Promise<PackageRelease[]> {
  const path = `/v1/packages/${databaseId.split("/").map(encodeURIComponent).join("/")}`;
  const data = await requestJson<{ items?: PackageRelease[] }>(path, { token });
  return Array.isArray(data.items) ? data.items : [];
}

function packageIdPath(databaseId: string): string {
  return databaseId.split("/").map(encodeURIComponent).join("/");
}

/** Keep ``sha256:`` colon unescaped (matches Registry path regex). */
function digestPath(digest: string): string {
  if (digest.startsWith("sha256:")) {
    return `sha256:${encodeURIComponent(digest.slice("sha256:".length))}`;
  }
  return encodeURIComponent(digest);
}

export async function listPackageFiles(
  databaseId: string,
  digest: string,
  token: string | null,
): Promise<{ items: FileItem[]; digest: string; version?: string }> {
  const id = packageIdPath(databaseId);
  const dig = digestPath(digest);
  return requestJson(`/v1/packages/${id}/by-digest/${dig}/files`, { token });
}

export async function getPackageFile(
  databaseId: string,
  digest: string,
  filePath: string,
  token: string | null,
): Promise<FileContent> {
  const id = packageIdPath(databaseId);
  const dig = digestPath(digest);
  const fp = filePath
    .split("/")
    .map((s) => encodeURIComponent(s))
    .join("/");
  return requestJson(`/v1/packages/${id}/by-digest/${dig}/files/${fp}`, { token });
}

export async function listSuites(
  databaseId: string,
  token: string | null,
): Promise<SuiteRow[]> {
  const q = new URLSearchParams({ database_id: databaseId });
  const data = await requestJson<{ items?: SuiteRow[] }>(
    `/v1/results/suites?${q.toString()}`,
    { token },
  );
  return Array.isArray(data.items) ? data.items : [];
}

export async function deviceCode(): Promise<{
  device_code: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete?: string;
  interval?: number;
  expires_in?: number;
}> {
  return requestJson("/v1/auth/github/device/code", {
    method: "POST",
    body: {},
  });
}

export async function devicePoll(
  deviceCodeValue: string,
): Promise<{ status?: string; access_token?: string; token?: string }> {
  return requestJson("/v1/auth/github/device/poll", {
    method: "POST",
    body: { device_code: deviceCodeValue },
  });
}

/** Prefer file entries under tasks/<id>/ (exclude dirs). */
export function filesToTree(items: FileItem[], prefix?: string): TreeEntry[] {
  const files = items.filter((i) => i.type !== "dir");
  const filtered = prefix
    ? files.filter((i) => i.path === prefix || i.path.startsWith(prefix + "/"))
    : files;
  return filtered
    .map((i) => ({
      path: i.path,
      name: i.path.split("/").pop() || i.path,
      type: i.type,
      size: i.size,
    }))
    .sort((a, b) => a.path.localeCompare(b.path));
}

export function taskIdsFromFiles(items: FileItem[]): string[] {
  const ids = new Set<string>();
  for (const item of items) {
    const m = item.path.match(/^tasks\/([^/]+)/);
    if (m?.[1]) ids.add(m[1]);
  }
  return Array.from(ids).sort();
}

export function decodeFileContent(file: FileContent): string {
  if (file.encoding === "base64") {
    try {
      const bin = atob(file.content);
      const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
      return new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    } catch {
      return "[binary content]";
    }
  }
  return file.content;
}
