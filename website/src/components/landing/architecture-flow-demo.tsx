"use client";

import { useState } from "react";
import styles from "./landing.module.css";

type FlowNode = {
  id: string;
  label: string;
  kind: string;
  responsibility: string;
  input: string;
  output: string;
};

type FlowScenario = {
  id: string;
  tab: string;
  title: string;
  summary: string;
  nodes: readonly FlowNode[];
};

const copy = {
  "zh-CN": {
    scenarioLabel: "BORA 架构路径",
    fields: ["职责", "输入", "输出"],
    state: "设计路径",
    scenarios: [
      {
        id: "lock",
        tab: "配置锁定",
        title: "从 Dataset 得到唯一执行身份",
        summary:
          "Config Core 读取根 bora.yaml 与成员 task.yaml，合并 envelope 与 allowlisted overrides，产出不可变 lock 摘要。",
        nodes: [
          {
            id: "database",
            label: "Database root",
            kind: "INDEX",
            responsibility: "suite identity、成员定位、分发元数据",
            input: "bora.yaml",
            output: "Selected task id",
          },
          {
            id: "task",
            label: "Task member",
            kind: "AUTHORING",
            responsibility: "harness / evaluator / profiles / limits / provider",
            input: "tasks/<id>/task.yaml",
            output: "Validated task source",
          },
          {
            id: "lock",
            label: "load_and_lock",
            kind: "TRUSTED",
            responsibility: "唯一规范读取者；计算 digest；拒绝非法 override",
            input: "Package + CLI --set",
            output: "Locked snapshot",
          },
          {
            id: "digest",
            label: "Lock digest",
            kind: "IMMUTABLE",
            responsibility: "正式 Attempt 的输入权威",
            input: "Canonical task",
            output: "Execution identity",
          },
        ],
      },
      {
        id: "execute",
        tab: "Attempt 执行",
        title: "Harness 写 loop，Core 守边界",
        summary:
          "Harness 经 SDK 打开 session 并 invoke；Agent 走 ACP entry；Provider 投影 workspace 与 credential；硬顶在 effect 前生效。",
        nodes: [
          {
            id: "attempt",
            label: "Attempt",
            kind: "ISOLATION",
            responsibility: "Run/Trial/Attempt 身份与生命周期",
            input: "Lock + provider plan",
            output: "Attempt context",
          },
          {
            id: "harness",
            label: "Package harness",
            kind: "WORKFLOW",
            responsibility: "业务 loop、角色、本地 Tool、handoff 数据",
            input: "ctx.params + SDK",
            output: "Session invokes",
          },
          {
            id: "acp",
            label: "ACP inlet",
            kind: "AGENT",
            responsibility: "parent 唯一 client；entry 在进程外翻译 vendor 协议",
            input: "executor: acp + entry",
            output: "AgentResult + evidence",
          },
          {
            id: "provider",
            label: "Provider",
            kind: "PROJECTION",
            responsibility: "host 或 Docker L1；mount / UID / network / secrets",
            input: "Workspace plan",
            output: "Bounded execution target",
          },
        ],
      },
      {
        id: "evaluate",
        tab: "评测与证据",
        title: "运行事实与 PASS 分开封存",
        summary:
          "Evaluator 在 barrier 后拿到 materialize 的输入；Core 绑定结果。轨迹与 usage 只作观测，不得充当 PASS。",
        nodes: [
          {
            id: "barrier",
            label: "Evaluator barrier",
            kind: "BOUNDARY",
            responsibility: "停止 writer；materialize gold / hidden inputs",
            input: "Harness terminal",
            output: "Clean eval inputs",
          },
          {
            id: "evaluator",
            label: "Package evaluator",
            kind: "SCORE",
            responsibility: "算法与真值；不启 Agent、不持 host secret",
            input: "Artifacts + gold",
            output: "Raw evaluation",
          },
          {
            id: "result",
            label: "Bound Result",
            kind: "AUTHORITY",
            responsibility: "Core 绑定 PASS/FAIL/ERROR 与 logs locator",
            input: "Runtime + eval facts",
            output: "Flat Result",
          },
          {
            id: "evidence",
            label: "Attempt evidence",
            kind: "AUDIT",
            responsibility: "invoke 树、trajectory、permission decision",
            input: "§8.9 layout",
            output: "view / export",
          },
        ],
      },
    ] satisfies FlowScenario[],
  },
  en: {
    scenarioLabel: "BORA architecture paths",
    fields: ["Owns", "Input", "Output"],
    state: "design path",
    scenarios: [
      {
        id: "lock",
        tab: "Lock",
        title: "One execution identity from a Dataset",
        summary:
          "Config Core reads root bora.yaml and member task.yaml, merges envelope and allowlisted overrides, and emits an immutable lock summary.",
        nodes: [
          {
            id: "database",
            label: "Database root",
            kind: "INDEX",
            responsibility: "Suite identity, member discovery, distribution metadata",
            input: "bora.yaml",
            output: "Selected task id",
          },
          {
            id: "task",
            label: "Task member",
            kind: "AUTHORING",
            responsibility: "Harness, evaluator, profiles, limits, provider",
            input: "tasks/<id>/task.yaml",
            output: "Validated task source",
          },
          {
            id: "lock",
            label: "load_and_lock",
            kind: "TRUSTED",
            responsibility: "Sole normative reader; digest; reject illegal overrides",
            input: "Package + CLI --set",
            output: "Locked snapshot",
          },
          {
            id: "digest",
            label: "Lock digest",
            kind: "IMMUTABLE",
            responsibility: "Input authority for formal Attempts",
            input: "Canonical task",
            output: "Execution identity",
          },
        ],
      },
      {
        id: "execute",
        tab: "Attempt",
        title: "Harness owns the loop; Core owns the boundary",
        summary:
          "Harness opens sessions via the SDK. Agents enter through ACP. Provider projects workspace and credentials. Hard ceilings apply before effects.",
        nodes: [
          {
            id: "attempt",
            label: "Attempt",
            kind: "ISOLATION",
            responsibility: "Run/Trial/Attempt identity and lifecycle",
            input: "Lock + provider plan",
            output: "Attempt context",
          },
          {
            id: "harness",
            label: "Package harness",
            kind: "WORKFLOW",
            responsibility: "Business loop, roles, local tools, handoff data",
            input: "ctx.params + SDK",
            output: "Session invokes",
          },
          {
            id: "acp",
            label: "ACP inlet",
            kind: "AGENT",
            responsibility: "One parent client; vendor translation outside BORA",
            input: "executor: acp + entry",
            output: "AgentResult + evidence",
          },
          {
            id: "provider",
            label: "Provider",
            kind: "PROJECTION",
            responsibility: "Host or Docker L1; mounts, UID, network, secrets",
            input: "Workspace plan",
            output: "Bounded execution target",
          },
        ],
      },
      {
        id: "evaluate",
        tab: "Evaluate",
        title: "Seal runtime facts separately from PASS",
        summary:
          "After the barrier, the evaluator receives materialized inputs. Core binds the result. Trajectory and usage are observational only.",
        nodes: [
          {
            id: "barrier",
            label: "Evaluator barrier",
            kind: "BOUNDARY",
            responsibility: "Stop writers; materialize gold / hidden inputs",
            input: "Harness terminal",
            output: "Clean eval inputs",
          },
          {
            id: "evaluator",
            label: "Package evaluator",
            kind: "SCORE",
            responsibility: "Scoring algorithm only; no Agent, no host secrets",
            input: "Artifacts + gold",
            output: "Raw evaluation",
          },
          {
            id: "result",
            label: "Bound Result",
            kind: "AUTHORITY",
            responsibility: "Core binds PASS/FAIL/ERROR and logs locator",
            input: "Runtime + eval facts",
            output: "Flat Result",
          },
          {
            id: "evidence",
            label: "Attempt evidence",
            kind: "AUDIT",
            responsibility: "Invoke tree, trajectory, permission decisions",
            input: "§8.9 layout",
            output: "view / export",
          },
        ],
      },
    ] satisfies FlowScenario[],
  },
} as const;

export function ArchitectureFlowDemo({ lang }: { lang: "zh-CN" | "en" }) {
  const text = copy[lang];
  const [scenarioIndex, setScenarioIndex] = useState(0);
  const scenario = text.scenarios[scenarioIndex];
  const [selectedNodeId, setSelectedNodeId] = useState<string>(scenario.nodes[0].id);
  const selectedNode =
    scenario.nodes.find((node) => node.id === selectedNodeId) ?? scenario.nodes[0];

  function selectScenario(index: number) {
    const next = text.scenarios[index];
    setScenarioIndex(index);
    setSelectedNodeId(next.nodes[0].id);
  }

  return (
    <div className={styles.flowDemo}>
      <div className={styles.flowDemoHeader}>
        <div className={styles.flowTabs} role="tablist" aria-label={text.scenarioLabel}>
          {text.scenarios.map((item, index) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`architecture-tab-${item.id}`}
              aria-controls="architecture-scenario-panel"
              aria-selected={index === scenarioIndex}
              className={styles.flowTab}
              onClick={() => selectScenario(index)}
            >
              {item.tab}
            </button>
          ))}
        </div>
      </div>

      <div
        id="architecture-scenario-panel"
        role="tabpanel"
        aria-labelledby={`architecture-tab-${scenario.id}`}
        className={styles.flowScenarioCopy}
      >
        <h2>{scenario.title}</h2>
        <p>{scenario.summary}</p>
      </div>

      <div className={styles.flowWorkspace}>
        <div className={styles.simpleFlowCanvas} role="region" aria-label={scenario.title}>
          <ol className={styles.simpleFlowGrid}>
            {scenario.nodes.map((node, index) => (
              <li key={node.id}>
                <button
                  type="button"
                  className={styles.flowNode}
                  data-state="completed"
                  data-selected={selectedNodeId === node.id}
                  aria-label={`${node.label}: ${text.state}`}
                  aria-pressed={selectedNodeId === node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                >
                  <span className={styles.flowNodeKind}>{node.kind}</span>
                  <strong>{node.label}</strong>
                  <span className={styles.flowNodeStatus}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        <aside className={styles.flowInspector} aria-live="polite">
          <div className={styles.flowInspectorHeading}>
            <span>{selectedNode.kind}</span>
            <strong>{selectedNode.label}</strong>
          </div>
          <dl>
            <div>
              <dt>{text.fields[0]}</dt>
              <dd>{selectedNode.responsibility}</dd>
            </div>
            <div>
              <dt>{text.fields[1]}</dt>
              <dd>{selectedNode.input}</dd>
            </div>
            <div>
              <dt>{text.fields[2]}</dt>
              <dd>{selectedNode.output}</dd>
            </div>
          </dl>
        </aside>
      </div>
    </div>
  );
}
