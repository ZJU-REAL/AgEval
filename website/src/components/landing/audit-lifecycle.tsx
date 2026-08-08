"use client";

import styles from "./landing.module.css";

const copy = {
  "zh-CN": {
    steps: [
      {
        title: "Session invoke",
        authority: "Harness + Agent Service",
        detail: "SDK session 打开后每次 invoke 写入 Attempt evidence；ACP permission 决策可审计。",
      },
      {
        title: "Trajectory seal",
        authority: "Evidence store",
        detail: "轨迹与 runtime outcome 落盘；缺轨迹不得发明 PASS。",
      },
      {
        title: "Evaluator barrier",
        authority: "Core",
        detail: "停止 harness writer；按 allowlist materialize gold / hidden 给 clean evaluator。",
      },
      {
        title: "Bound verdict",
        authority: "Evaluator + Core",
        detail: "PASS/FAIL/ERROR 绑定 run identity；CLI 分离展示 runtime 与 evaluation。",
      },
    ],
  },
  en: {
    steps: [
      {
        title: "Session invoke",
        authority: "Harness + Agent Service",
        detail:
          "Each SDK invoke writes Attempt evidence. ACP permission decisions stay auditable.",
      },
      {
        title: "Trajectory seal",
        authority: "Evidence store",
        detail: "Trajectory and runtime outcomes land on disk. Missing trajectory must not invent PASS.",
      },
      {
        title: "Evaluator barrier",
        authority: "Core",
        detail:
          "Stop harness writers. Materialize gold / hidden inputs for a clean evaluator only.",
      },
      {
        title: "Bound verdict",
        authority: "Evaluator + Core",
        detail:
          "PASS/FAIL/ERROR bind to run identity. CLI separates runtime facts from evaluation.",
      },
    ],
  },
} as const;

export function AuditLifecycle({ lang }: { lang: "zh-CN" | "en" }) {
  const steps = copy[lang].steps;
  return (
    <ol className={styles.auditList}>
      {steps.map((step, index) => (
        <li key={step.title} className={styles.auditItem}>
          <span className={styles.auditIndex}>{String(index + 1).padStart(2, "0")}</span>
          <div>
            <h3>{step.title}</h3>
            <p className={styles.auditAuthority}>{step.authority}</p>
            <p>{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
