/**
 * Mock Leaderboard suite rows with / without pass@k for local Hub smoke (#60 C4).
 * Observational metrics only — not suite PASS. k is not a job identity key.
 */
import type { SuiteRow } from "@/lib/api";

const kCell = (value: number, nTasks = 2, incomplete = 0) => ({
  value,
  n_tasks: nTasks,
  incomplete_tasks: incomplete,
});

/** Two jobs: one Always-k=4 with pass@k, one legacy k=1 without k maps. */
export const LEADERBOARD_K_FIXTURES: SuiteRow[] = [
  {
    suite_run_id: "suite_demo_k4_high",
    database_id: "demo/pass-at-k",
    database_version: "0.1.0",
    visibility: "public",
    pass_rate: 0.5,
    mean_score: 0.5,
    agent_label: "codex@acp",
    model_label: "gpt-demo",
    metrics: {
      pass_rate: 0.5,
      mean_score: 0.5,
      n_tasks: 2,
      n_pass: 1,
      n_fail: 1,
      n_error: 0,
      missing_score_as: 0.0,
      n_attempts: 4,
      k_values: [1, 2, 4],
      pass_at_k: {
        "1": kCell(0.5),
        "2": kCell(0.625),
        "4": kCell(0.75),
      },
      pass_power_k: {
        "1": kCell(0.5),
        "2": kCell(0.25),
        "4": kCell(0.0625),
      },
      per_task: [
        { task_id: "a", n: 4, c: 3, status: "PASS" },
        { task_id: "b", n: 4, c: 1, status: "PASS" },
      ],
    },
    task_refs: [
      {
        task_id: "a",
        status: "PASS",
        score: 0.75,
        run_id: "a0",
        n: 4,
        c: 3,
        attempt_run_ids: ["a0", "a1", "a2", "a3"],
      },
      {
        task_id: "b",
        status: "PASS",
        score: 0.25,
        run_id: "b0",
        n: 4,
        c: 1,
        attempt_run_ids: ["b0", "b1", "b2", "b3"],
      },
    ],
    job_overlay: {
      bindings: {
        solver: {
          executor: "acp",
          options: { entry: "codex" },
          model: "gpt-demo",
          api_key: "OPENAI_API_KEY",
        },
      },
    },
    plugins: [{ plugin_id: "nooa", version: "0.1.0" }],
    created_at: 1_700_000_100,
    note: "per-task evaluator verdicts only; no suite-level PASS",
  },
  {
    suite_run_id: "suite_demo_legacy_no_k",
    database_id: "demo/pass-at-k",
    database_version: "0.1.0",
    visibility: "public",
    pass_rate: 0.75,
    mean_score: 0.7,
    agent_label: "pi@acp",
    model_label: "local-demo",
    metrics: {
      pass_rate: 0.75,
      mean_score: 0.7,
      n_tasks: 4,
      n_pass: 3,
      n_fail: 1,
      n_error: 0,
      missing_score_as: 0.0,
    },
    task_refs: [
      { task_id: "a", status: "PASS", score: 1.0, run_id: "r1" },
      { task_id: "b", status: "PASS", score: 1.0, run_id: "r2" },
      { task_id: "c", status: "PASS", score: 0.8, run_id: "r3" },
      { task_id: "d", status: "FAIL", score: 0.0, run_id: "r4" },
    ],
    job_overlay: {
      bindings: {
        solver: {
          executor: "acp",
          options: { entry: "pi" },
          model: "local-demo",
        },
      },
    },
    created_at: 1_700_000_000,
    note: "per-task evaluator verdicts only; no suite-level PASS",
  },
];
