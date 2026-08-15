/** Registry HTTP client for Hub SPA (#39 / #40). */

export type DeclaredSlot = {
  id: string;
  kind: "provide" | "on" | string;
  entry?: string;
  priority?: number;
  level?: number;
};

export type PluginPreview = {
  plugin_id?: string;
  version?: string;
  format?: string;
  slots?: {
    provide?: string[];
    on?: string[];
    [key: string]: unknown;
  };
  declared?: DeclaredSlot[];
  files?: string[];
};

export type SuitePluginRef = {
  plugin_id: string;
  version?: string;
};

const BUILTIN_EXECUTOR_KINDS = new Set(["acp", "openai-http"]);

export type PackageRelease = {
  database_id: string;
  version: string;
  visibility: string;
  package_digest: string;
  blob_digest: string;
  size: number;
  media_type?: string;
  /** Registry package_kind: database | plugin. */
  package_kind?: "database" | "plugin" | string;
  created_at?: number;
  org_id?: string;
  /** Registry marketplace display: upload org is on the official-org allowlist. */
  official?: boolean;
  /** Present on by-digest / version get for plugins. */
  plugin_preview?: PluginPreview;
  /** Draft slot (entitled callers only). */
  is_draft?: boolean;
  slot?: string;
  uploaded_by?: string;
  /** Owner-set marketplace title; id stays database_id. */
  display_name?: string;
};

export type OrgRow = {
  org_id: string;
  name: string;
  display_name?: string;
  is_claimable?: boolean;
  created_at?: number;
  role?: string;
  /** Upload org is on the Registry official-org allowlist. */
  official?: boolean;
};

export type OrgMember = {
  org_id: string;
  user_id: string;
  role: string;
  created_at?: number;
  /** GitHub profile display name (from login-time profile snapshot). */
  display_name?: string;
  avatar_url?: string;
  github_id?: string;
};

export type UserOfficialOrg = {
  org_id: string;
  display_name?: string;
  official: true;
};

export type UserPublic = {
  user_id: string;
  display_name?: string;
  avatar_url?: string;
  official: boolean;
  official_orgs: UserOfficialOrg[];
};

export type OrgInviteKey = {
  key_id: string;
  org_id: string;
  token_prefix: string;
  created_by?: string;
  max_uses?: number | null;
  use_count?: number;
  expires_at?: number | null;
  revoked_at?: number | null;
  created_at?: number;
  active?: boolean;
  /** Full secret — create response only; omitted from list/revoke. */
  invite_key?: string;
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
  /**
   * Observational suite metrics blob (Registry metrics_json).
   * May include pass_at_k / pass_power_k / n_attempts / k_values / per_task (#60).
   * Never suite-level PASS.
   */
  metrics?: Record<string, unknown>;
  task_refs?: Array<{
    task_id?: string;
    status?: string | null;
    score?: number | null;
    run_id?: string | null;
    /** Multi-attempt sample counts (#60 A3). */
    n?: number | null;
    c?: number | null;
    /** All attempt run_ids for audit / --with-attempts. */
    attempt_run_ids?: string[];
    /** True when full Attempt evidence archive is present on Registry (#43). */
    has_attempt_content?: boolean;
  }>;
  agent_label?: string;
  model_label?: string;
  config_fingerprint?: string;
  config_homogeneous?: boolean;
  actors_summary?: Array<Record<string, string>>;
  /** Secret-free job binding (#59) for rehydrate / re-run. */
  job_overlay?: {
    bindings?: Record<
      string,
      {
        executor?: string;
        model?: string;
        base_url?: string;
        api_key?: string;
        options?: { entry?: string };
      }
    >;
  };
  /** Secret-free marketplace plugins used by this job. */
  plugins?: SuitePluginRef[];
  exit_code?: number | null;
  created_at?: number | string;
  note?: string;
  uploaded_by?: string;
  /** Stored at upload; complete ≠ suite PASS. */
  complete?: boolean;
  bound_kind?: "release" | "draft" | "unknown" | string;
  task_set_digest?: string;
};

export type AttemptMeta = {
  run_id: string;
  database_id?: string;
  task_id?: string;
  status?: string;
  visibility?: string;
  blob_digest?: string;
  size?: number;
  created_at?: number | string;
  uploaded_by?: string;
  suite_run_id?: string;
  lock_digest?: string;
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

/** Hub plugin/package id is ``org/name``. Display edits only the name leaf. */
export function splitPackageId(id: string): { org: string | null; name: string } {
  const slash = id.indexOf("/");
  if (slash <= 0 || slash === id.length - 1) return { org: null, name: id };
  return { org: id.slice(0, slash), name: id.slice(slash + 1) };
}

export function packageDisplayTitle(id: string, displayName?: string | null): string {
  const { org, name } = splitPackageId(id);
  const leaf = (displayName || "").trim() || name;
  return org ? `${org}/${leaf}` : leaf;
}

export function decodeDatasetId(param: string): string {
  return decodeURIComponent(param);
}

export async function listPackages(
  token: string | null,
  opts?: { packageKind?: "database" | "plugin"; mine?: boolean },
): Promise<PackageRelease[]> {
  // With token, server may include private; without, public only.
  const q = new URLSearchParams();
  if (opts?.packageKind) q.set("package_kind", opts.packageKind);
  if (opts?.mine) q.set("mine", "1");
  const path = q.toString() ? `/v1/packages?${q.toString()}` : "/v1/packages";
  const data = await requestJson<{ items?: PackageRelease[] }>(path, {
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

/** Package meta by digest (includes plugin_preview for bora.plugin/1). */
export async function getPackageByDigest(
  packageId: string,
  digest: string,
  token: string | null,
): Promise<PackageRelease> {
  const id = packageIdPath(packageId);
  const dig = digestPath(digest);
  return requestJson(`/v1/packages/${id}/by-digest/${dig}`, { token });
}

export function isDraftRelease(row: PackageRelease): boolean {
  return Boolean(row.is_draft || row.slot === "draft" || row.version === "draft");
}

export function versionLabel(row: PackageRelease): string {
  return isDraftRelease(row) ? "draft" : `v${row.version}`;
}

/** Prefer latest release; fall back to draft when that is the only slot. */
export function pickPackageVersion(
  versions: PackageRelease[],
  requested?: string | null,
): PackageRelease | null {
  if (!versions.length) return null;
  if (requested) {
    const hit = versions.find((v) => v.version === requested);
    if (hit) return hit;
  }
  const releases = versions.filter((v) => !isDraftRelease(v));
  const pool = releases.length ? releases : versions;
  return [...pool].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))[0];
}

/** One catalog row per database_id. Draft is never preferred over a release. */
export function latestPackageByDatabase(
  items: PackageRelease[],
): PackageRelease[] {
  const byId = new Map<string, PackageRelease[]>();
  for (const row of items) {
    const list = byId.get(row.database_id) ?? [];
    list.push(row);
    byId.set(row.database_id, list);
  }
  const out: PackageRelease[] = [];
  for (const rows of byId.values()) {
    const picked = pickPackageVersion(rows);
    if (picked) out.push(picked);
  }
  return out.sort((a, b) => a.database_id.localeCompare(b.database_id));
}

export function isPluginPackage(row: PackageRelease): boolean {
  return row.package_kind === "plugin";
}

export function isDatabasePackage(row: PackageRelease): boolean {
  return !isPluginPackage(row);
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
  opts?: { board?: boolean; uploadedBy?: string },
): Promise<SuiteRow[]> {
  const q = new URLSearchParams();
  if (databaseId) q.set("database_id", databaseId);
  if (opts?.board) q.set("board", "1");
  if (opts?.uploadedBy) q.set("uploaded_by", opts.uploadedBy);
  const path = q.toString()
    ? `/v1/results/suites?${q.toString()}`
    : "/v1/results/suites";
  const data = await requestJson<{ items?: SuiteRow[] }>(path, { token });
  return Array.isArray(data.items) ? data.items : [];
}

export async function getAttempt(
  runId: string,
  token: string | null,
): Promise<AttemptMeta> {
  return requestJson(`/v1/results/attempts/${encodeURIComponent(runId)}`, {
    token,
  });
}

export async function listAttemptFiles(
  runId: string,
  token: string | null,
): Promise<{ run_id: string; items: FileItem[]; digest?: string }> {
  return requestJson(
    `/v1/results/attempts/${encodeURIComponent(runId)}/files`,
    { token },
  );
}

export async function getAttemptFile(
  runId: string,
  filePath: string,
  token: string | null,
): Promise<FileContent> {
  const fp = filePath
    .split("/")
    .map((s) => encodeURIComponent(s))
    .join("/");
  return requestJson(
    `/v1/results/attempts/${encodeURIComponent(runId)}/files/${fp}`,
    { token },
  );
}

export async function getUser(userId: string): Promise<UserPublic> {
  return requestJson(`/v1/users/${encodeURIComponent(userId)}`);
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

export async function updateOrgDisplayName(
  orgId: string,
  displayName: string,
  token: string | null,
): Promise<OrgRow> {
  return requestJson(`/v1/orgs/${encodeURIComponent(orgId)}`, {
    token,
    method: "PATCH",
    body: { display_name: displayName },
  });
}

export async function updatePackageDisplayName(
  packageId: string,
  displayName: string,
  token: string | null,
): Promise<PackageRelease> {
  return requestJson(`/v1/packages/${packageIdPath(packageId)}`, {
    token,
    method: "PATCH",
    body: { display_name: displayName },
  });
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

export async function joinOrgWithInvite(
  inviteKey: string,
  token: string | null,
): Promise<OrgRow & { role?: string }> {
  return requestJson("/v1/orgs/join", {
    token,
    method: "POST",
    body: { invite_key: inviteKey },
  });
}

export async function listOrgInviteKeys(
  orgId: string,
  token: string | null,
): Promise<OrgInviteKey[]> {
  const data = await requestJson<{ items?: OrgInviteKey[] }>(
    `/v1/orgs/${encodeURIComponent(orgId)}/invite-keys`,
    { token },
  );
  return Array.isArray(data.items) ? data.items : [];
}

export async function createOrgInviteKey(
  orgId: string,
  body: { max_uses?: number | null; expires_in_days?: number | null },
  token: string | null,
): Promise<OrgInviteKey> {
  return requestJson(`/v1/orgs/${encodeURIComponent(orgId)}/invite-keys`, {
    token,
    method: "POST",
    body,
  });
}

export async function revokeOrgInviteKey(
  orgId: string,
  keyId: string,
  token: string | null,
): Promise<OrgInviteKey> {
  return requestJson(
    `/v1/orgs/${encodeURIComponent(orgId)}/invite-keys/${encodeURIComponent(keyId)}`,
    { token, method: "DELETE" },
  );
}

/** Current user leaves org (sole owner must dissolve instead). */
export async function leaveOrg(
  orgId: string,
  token: string | null,
): Promise<{ ok: boolean; org_id: string }> {
  return requestJson(`/v1/orgs/${encodeURIComponent(orgId)}/leave`, {
    token,
    method: "POST",
    body: {},
  });
}

/** Owner dissolves org (fails if packages still bound). */
export async function dissolveOrg(
  orgId: string,
  token: string | null,
): Promise<{ ok: boolean; org_id: string }> {
  return requestJson(`/v1/orgs/${encodeURIComponent(orgId)}`, {
    token,
    method: "DELETE",
  });
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

/** Hub browser OAuth (Authorization Code) — Harbor-style, no device user_code. */
export async function startWebLogin(
  redirectUri: string,
): Promise<{ authorize_url: string; state: string }> {
  return requestJson("/v1/auth/github/web/start", {
    method: "POST",
    body: { redirect_uri: redirectUri },
  });
}

export async function completeWebLogin(opts: {
  code: string;
  state: string;
  redirectUri: string;
}): Promise<{
  token: string;
  github_user?: string;
  github_name?: string;
  github_id?: number;
  avatar_url?: string;
  scopes?: string[];
}> {
  return requestJson("/v1/auth/github/web/callback", {
    method: "POST",
    body: {
      code: opts.code,
      state: opts.state,
      redirect_uri: opts.redirectUri,
    },
  });
}

/**
 * Device poll. Registry returns 202 while pending (not an error).
 * Success 200: ``{ token, github_user, scopes }`` (Registry API token, not GH).
 */
export async function devicePoll(
  deviceCodeValue: string,
  opts?: { signal?: AbortSignal },
): Promise<{
  status?: string;
  token?: string;
  access_token?: string;
  github_user?: string;
  github_name?: string;
  github_id?: number;
  avatar_url?: string;
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
    signal: opts?.signal,
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
    github_name:
      typeof data.github_name === "string" ? data.github_name : undefined,
    github_id: typeof data.github_id === "number" ? data.github_id : undefined,
    avatar_url:
      typeof data.avatar_url === "string" ? data.avatar_url : undefined,
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

/** True when package digest listing includes Dataset-level shared/ (#65). */
export function hasSharedFiles(items: FileItem[]): boolean {
  return items.some(
    (i) => i.path === "shared" || i.path.startsWith("shared/"),
  );
}

/** Total byte size of file entries under shared/ (dirs size 0). */
export function sharedFilesStats(items: FileItem[]): {
  fileCount: number;
  totalBytes: number;
} {
  let fileCount = 0;
  let totalBytes = 0;
  for (const i of items) {
    if (i.type === "dir") continue;
    if (i.path === "shared" || i.path.startsWith("shared/")) {
      fileCount += 1;
      totalBytes += i.size || 0;
    }
  }
  return { fileCount, totalBytes };
}

/**
 * Suite rows store the local plugin.yaml id (`nooa`). Marketplace routes use
 * the Registry package id (`my-lab/nooa`). Map when a catalog is available.
 */
export function resolveMarketplacePluginId(
  pluginId: string,
  catalog: PackageRelease[],
  preferredOrgId?: string | null,
): string {
  const id = pluginId.trim();
  if (!id) return id;
  if (catalog.some((p) => p.database_id === id)) return id;

  const previewHits = catalog.filter((p) => p.plugin_preview?.plugin_id === id);
  const suffixHits = catalog.filter((p) => {
    const db = p.database_id;
    return db === id || db.endsWith(`/${id}`);
  });

  const pick = (rows: PackageRelease[]): PackageRelease | undefined => {
    if (!rows.length) return undefined;
    if (preferredOrgId) {
      const org = preferredOrgId;
      const hit = rows.find(
        (p) => p.org_id === org || p.database_id.startsWith(`${org}/`),
      );
      if (hit) return hit;
    }
    return rows[0];
  };

  return (
    pick(previewHits)?.database_id ?? pick(suffixHits)?.database_id ?? id
  );
}

/** Marketplace plugins for a suite row (stored list, else executor inference). */
export function pluginsUsedBySuite(
  suite: SuiteRow,
  catalog: PackageRelease[] = [],
  preferredOrgId?: string | null,
): SuitePluginRef[] {
  const stored = Array.isArray(suite.plugins) ? suite.plugins : [];
  const fromStore: SuitePluginRef[] = [];
  const seen = new Set<string>();
  for (const raw of stored) {
    const id = String(raw?.plugin_id || "").trim();
    const key = id.toLowerCase();
    if (!id || seen.has(key) || BUILTIN_EXECUTOR_KINDS.has(key) || key === "default") {
      continue;
    }
    seen.add(key);
    const marketplaceId = resolveMarketplacePluginId(
      id,
      catalog,
      preferredOrgId,
    );
    const version = String(raw.version || "").trim();
    fromStore.push(
      version
        ? { plugin_id: marketplaceId, version }
        : { plugin_id: marketplaceId },
    );
  }
  if (fromStore.length) return fromStore;
  const bindings = suite.job_overlay?.bindings;
  if (!bindings || typeof bindings !== "object") return [];
  for (const raw of Object.values(bindings)) {
    const exec = String(raw?.executor || "").trim();
    const key = exec.toLowerCase();
    if (!exec || seen.has(key) || BUILTIN_EXECUTOR_KINDS.has(key) || key === "default") {
      continue;
    }
    seen.add(key);
    fromStore.push({
      plugin_id: resolveMarketplacePluginId(exec, catalog, preferredOrgId),
    });
  }
  return fromStore;
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
