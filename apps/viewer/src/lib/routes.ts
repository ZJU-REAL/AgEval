import type { Job, TaskRow } from "@/lib/api";

export function enc(value: string): string {
  return encodeURIComponent(value);
}

export function jobPath(jobId: string): string {
  return `/jobs/${enc(jobId)}`;
}

export function taskPath(jobId: string, taskId: string): string {
  return `/jobs/${enc(jobId)}/tasks/${enc(taskId)}`;
}

export function trialPath(jobId: string, taskId: string, runId: string): string {
  return `/jobs/${enc(jobId)}/tasks/${enc(taskId)}/trials/${enc(runId)}`;
}

export function taskRunIds(task: Pick<TaskRow, "attempt_run_ids" | "run_id">): string[] {
  if (task.attempt_run_ids?.length) {
    return task.attempt_run_ids.filter(Boolean);
  }
  return task.run_id ? [task.run_id] : [];
}

export function jobDisplayName(job: Job): string {
  if (job.source_kind === "single") {
    return job.task_id || job.source || job.job_name;
  }
  return job.job_name;
}

/** Suite jobs open the task table; single-task jobs skip straight to the trial. */
export function jobHref(job: Job): string {
  if (job.source_kind === "single") {
    const taskId = job.task_id || job.source;
    const runId = job.run_id || job.job_id;
    if (taskId && runId) {
      return trialPath(job.job_id, taskId, runId);
    }
  }
  return jobPath(job.job_id);
}

/** One attempt → trial; k>1 → this job's filtered trial list. */
export function taskHref(jobId: string, task: TaskRow): string {
  const ids = taskRunIds(task);
  if (ids.length === 1) {
    return trialPath(jobId, task.task_id, ids[0]);
  }
  return taskPath(jobId, task.task_id);
}
