export type Job = {
  job_id: string;
  job_name: string;
  source: string;
  database_id?: string | null;
  database_version?: string | null;
  agent_label?: string;
  model_label?: string;
  provider_label?: string;
  environment?: string;
  result?: number | null;
  pass_rate?: number | null;
  mean_score?: number | null;
  started?: string | null;
  duration?: string | null;
  trials_done?: number;
  trials_total?: number;
  exit_code?: number | null;
  task_count?: number;
  note?: string;
};

export type TaskRow = {
  task_id: string;
  status?: string | null;
  score?: number | null;
  run_id?: string | null;
  error?: string | null;
  exit_code?: number | null;
  agent_label?: string;
  model_label?: string;
  provider_label?: string;
  dataset?: string | null;
  duration?: string | null;
};

export type Trial = {
  trial_id: string;
  task_id: string;
  status?: string | null;
  reward?: number | null;
  score?: number | null;
  duration?: string | null;
  started?: string | null;
  error?: string | null;
  run_id?: string | null;
  exit_code?: number | null;
  has_evidence?: boolean;
  available_tabs?: string[];
  evidence_relpath?: string | null;
  agent_invocations?: number | null;
  harness_kind?: string | null;
  /** Framework kind, e.g. acp */
  framework?: string | null;
  /** Docker placement label when L1/docker, else null */
  docker?: string | null;
  /** Per-role rows for the actors table above Trajectory */
  actors?: Array<{
    role: string;
    agent: string;
    model?: string | null;
    profile_id?: string;
  }>;
  agent_label?: string | null;
  model_label?: string | null;
  executor_kind?: string | null;
  note?: string | null;
};

export type TreeEntry = {
  path: string;
  name: string;
  type: "file" | "dir";
  size?: number | null;
};

export type TrajectoryStep = {
  type?: string;
  role?: string | null;
  content?: string | null;
  turn_index?: number | null;
  source?: string | null;
  stop_reason?: string | null;
  ok?: boolean | null;
  error?: string | null;
  invocation?: string;
  invocation_id?: string;
  line?: number;
  usage?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
};

export type Breadcrumb = { label: string; href: string | null };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  const data = (await res.json().catch(() => ({}))) as {
    error?: string;
    message?: string;
  } & T;
  if (!res.ok) {
    throw new Error(data.message || data.error || `HTTP ${res.status}`);
  }
  return data as T;
}

export function fetchJobs() {
  return getJson<{
    ok: boolean;
    items: Job[];
    count: number;
    database_id?: string;
    version?: string;
    root?: string;
    commands?: Record<string, string>;
  }>("/api/jobs");
}

export function fetchJob(jobId: string) {
  return getJson<{
    ok: boolean;
    job: Job;
    tasks: TaskRow[];
    task_count: number;
    commands?: Record<string, string>;
    note?: string;
  }>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchJobTask(jobId: string, taskId: string) {
  return getJson<{
    ok: boolean;
    job: Job;
    task: TaskRow;
    trials: Trial[];
    agent_label?: string;
    model_label?: string;
    provider_label?: string;
    dataset?: string;
    commands?: Record<string, string>;
    run_command?: string;
    breadcrumb: Breadcrumb[];
    note?: string;
  }>(
    `/api/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}`,
  );
}

function trialBase(jobId: string, taskId: string, runId: string) {
  return `/api/jobs/${encodeURIComponent(jobId)}/tasks/${encodeURIComponent(taskId)}/trials/${encodeURIComponent(runId)}`;
}

export function fetchTrial(jobId: string, taskId: string, runId: string) {
  return getJson<{
    ok: boolean;
    job: Job;
    task_id: string;
    trial: Trial;
    result?: Record<string, unknown> | null;
    prev_run_id?: string | null;
    next_run_id?: string | null;
    sibling_run_ids?: string[];
    commands?: Record<string, string>;
    run_command?: string;
    breadcrumb: Breadcrumb[];
    note?: string;
  }>(trialBase(jobId, taskId, runId));
}

export function fetchTrialTree(
  jobId: string,
  taskId: string,
  runId: string,
  scope: string,
) {
  const q = new URLSearchParams({ scope });
  return getJson<{
    ok: boolean;
    run_id: string;
    scope: string;
    entries: TreeEntry[];
    truncated?: boolean;
    note?: string;
  }>(`${trialBase(jobId, taskId, runId)}/tree?${q}`);
}

export function fetchTrialFile(
  jobId: string,
  taskId: string,
  runId: string,
  path: string,
) {
  const q = new URLSearchParams({ path });
  return getJson<{
    ok: boolean;
    run_id: string;
    path: string;
    name: string;
    size: number;
    media_type: string;
    encoding: string;
    truncated?: boolean;
    content?: string | null;
    note?: string;
  }>(`${trialBase(jobId, taskId, runId)}/file?${q}`);
}

export function fetchTrialTrajectory(jobId: string, taskId: string, runId: string) {
  return getJson<{
    ok: boolean;
    run_id: string;
    task_id: string;
    steps: TrajectoryStep[];
    step_count: number;
    invocations: Array<{
      dirname: string;
      invocation_id?: string;
      profile_id?: string;
      executor_kind?: string;
      model?: string;
      status?: string;
      step_count?: number;
      has_trajectory?: boolean;
    }>;
    truncated?: boolean;
    note?: string;
  }>(`${trialBase(jobId, taskId, runId)}/trajectory`);
}
