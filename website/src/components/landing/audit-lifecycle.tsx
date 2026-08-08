"use client";

import { Fragment, useState } from "react";
import styles from "./landing.module.css";

const copy = {
  "zh-CN": {
    label: "BORA 从 session invoke 到 evaluation 的事实链",
    headers: ["阶段", "主要产物", "权威来源"],
    current: "当前阶段",
    stages: [
      {
        id: "invoke",
        label: "Session invoke",
        artifact: "AgentResult + permission decisions",
        authority: "Harness + Agent Service",
        nodes: ["SDK session", "ACP prompt", "Attempt evidence"],
      },
      {
        id: "seal",
        label: "Trajectory seal",
        artifact: "trajectory + runtime outcome",
        authority: "Evidence store",
        nodes: ["Invoke tree", "On-disk layout", "No invented PASS"],
      },
      {
        id: "barrier",
        label: "Evaluator barrier",
        artifact: "Clean eval inputs",
        authority: "Core",
        nodes: ["Stop writers", "Materialize gold", "Hidden allowlist"],
      },
      {
        id: "score",
        label: "Independent score",
        artifact: "Raw evaluation output",
        authority: "Package evaluator",
        nodes: ["Artifacts", "Gold / truth", "Score algorithm"],
      },
      {
        id: "bind",
        label: "Bound Result",
        artifact: "PASS / FAIL / ERROR + logs",
        authority: "Evaluator + Core",
        nodes: ["Run identity", "Separate facts", "CLI summary"],
      },
    ],
  },
  en: {
    label: "BORA fact chain from session invoke to evaluation",
    headers: ["Stage", "Primary artifact", "Authority"],
    current: "Current stage",
    stages: [
      {
        id: "invoke",
        label: "Session invoke",
        artifact: "AgentResult + permission decisions",
        authority: "Harness + Agent Service",
        nodes: ["SDK session", "ACP prompt", "Attempt evidence"],
      },
      {
        id: "seal",
        label: "Trajectory seal",
        artifact: "trajectory + runtime outcome",
        authority: "Evidence store",
        nodes: ["Invoke tree", "On-disk layout", "No invented PASS"],
      },
      {
        id: "barrier",
        label: "Evaluator barrier",
        artifact: "Clean eval inputs",
        authority: "Core",
        nodes: ["Stop writers", "Materialize gold", "Hidden allowlist"],
      },
      {
        id: "score",
        label: "Independent score",
        artifact: "Raw evaluation output",
        authority: "Package evaluator",
        nodes: ["Artifacts", "Gold / truth", "Score algorithm"],
      },
      {
        id: "bind",
        label: "Bound Result",
        artifact: "PASS / FAIL / ERROR + logs",
        authority: "Evaluator + Core",
        nodes: ["Run identity", "Separate facts", "CLI summary"],
      },
    ],
  },
} as const;

type StageId = (typeof copy)["zh-CN"]["stages"][number]["id"];

export function AuditLifecycle({ lang }: { lang: "zh-CN" | "en" }) {
  const text = copy[lang];
  const [activeStageId, setActiveStageId] = useState<StageId>(text.stages[0].id);
  const activeStage = text.stages.find((stage) => stage.id === activeStageId) ?? text.stages[0];

  return (
    <div className={styles.auditLifecycle} aria-label={text.label}>
      <div className={styles.auditTable}>
        <div className={styles.auditHeader} aria-hidden="true">
          {text.headers.map((header) => (
            <span key={header}>{header}</span>
          ))}
        </div>
        {text.stages.map((stage) => {
          const active = stage.id === activeStageId;
          return (
            <button
              key={stage.id}
              type="button"
              className={styles.auditRow}
              data-active={active}
              aria-pressed={active}
              onPointerEnter={() => setActiveStageId(stage.id)}
              onFocus={() => setActiveStageId(stage.id)}
              onClick={() => setActiveStageId(stage.id)}
            >
              <span>{stage.label}</span>
              <span>{stage.artifact}</span>
              <span>{stage.authority}</span>
            </button>
          );
        })}
      </div>

      <div className={styles.auditDiagram}>
        <div className={styles.auditDiagramHeading}>
          <span>{text.current}</span>
          <strong aria-live="polite">{activeStage.label}</strong>
        </div>
        <div className={styles.auditDiagramViewport}>
          {text.stages.map((stage) => {
            const active = stage.id === activeStageId;
            return (
              <div
                key={stage.id}
                className={styles.auditDiagramContent}
                data-active={active}
                aria-hidden={!active}
              >
                <div className={styles.auditFlow}>
                  {stage.nodes.map((node, index) => (
                    <Fragment key={node}>
                      <div className={styles.auditFlowNode}>
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <strong>{node}</strong>
                      </div>
                      {index < stage.nodes.length - 1 ? (
                        <span className={styles.auditFlowConnector} aria-hidden="true">
                          →
                        </span>
                      ) : null}
                    </Fragment>
                  ))}
                </div>
                <p>
                  <span>{text.headers[2]}</span>
                  {stage.authority}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
