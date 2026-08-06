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
