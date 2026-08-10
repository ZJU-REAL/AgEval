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
  org_id?: string;
};

export type OrgRow = {
  org_id: string;
  name: string;
  display_name?: string;
  is_claimable?: boolean;
  created_at?: number;
  role?: string;
};

export type OrgMember = {
  org_id: string;
  user_id: string;
  role: string;
  created_at?: number;
};

export type ResultShare = {
  result_kind: string;
  result_id: string;
  target_type: string;
  target_id: string;
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
  uploaded_by?: string;
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
  databaseId: string | null,
  token: string | null,
): Promise<SuiteRow[]> {
  const q = new URLSearchParams();
  if (databaseId) q.set("database_id", databaseId);
  const path = q.toString()
    ? `/v1/results/suites?${q.toString()}`
    : "/v1/results/suites";
  const data = await requestJson<{ items?: SuiteRow[] }>(path, { token });
  return Array.isArray(data.items) ? data.items : [];
}

export async function listOrgs(token: string | null): Promise<OrgRow[]> {
  const data = await requestJson<{ items?: OrgRow[] }>("/v1/orgs", { token });
  return Array.isArray(data.items) ? data.items : [];
}

export async function getOrg(
  orgId: string,
  token: string | null,
): Promise<OrgRow> {
  return requestJson(`/v1/orgs/${encodeURIComponent(orgId)}`, { token });
}

export async function listOrgMembers(
  orgId: string,
  token: string | null,
): Promise<OrgMember[]> {
  const data = await requestJson<{ items?: OrgMember[] }>(
    `/v1/orgs/${encodeURIComponent(orgId)}/members`,
    { token },
  );
  return Array.isArray(data.items) ? data.items : [];
}

export async function listResultShares(
  kind: "attempt" | "suite",
  resultId: string,
  token: string | null,
): Promise<ResultShare[]> {
  const kindPath = kind === "attempt" ? "attempts" : "suites";
  const data = await requestJson<{ items?: ResultShare[] }>(
    `/v1/results/${kindPath}/${encodeURIComponent(resultId)}/shares`,
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

/**
 * Device poll. Registry returns 202 while pending (not an error).
 * Success 200: ``{ token, github_user, scopes }`` (Registry API token, not GH).
 */
export async function devicePoll(
  deviceCodeValue: string,
): Promise<{
  status?: string;
  token?: string;
  access_token?: string;
  github_user?: string;
  message?: string;
  error?: string;
}> {
  const url = `${registryBase()}/v1/auth/github/device/poll`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ device_code: deviceCodeValue }),
  });
  const text = await res.text();
  let data: Record<string, unknown> = {};
  try {
    data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
  } catch {
    data = { message: text };
  }
  // 202 Accepted = still waiting (must not throw — res.ok is true for 202,
  // but we normalize explicitly for clarity).
  if (res.status === 202 || data.status === "authorization_pending") {
    return {
      status: "authorization_pending",
      message: String(data.message || "waiting for user"),
    };
  }
  if (!res.ok) {
    throw new RegistryHttpError(
      res.status,
      String(data.error || "http_error"),
      String(data.message || res.statusText || "poll failed"),
    );
  }
  return {
    status: "ok",
    token: typeof data.token === "string" ? data.token : undefined,
    access_token:
      typeof data.access_token === "string" ? data.access_token : undefined,
    github_user:
      typeof data.github_user === "string" ? data.github_user : undefined,
  };
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
