import Link from "next/link";
import { ArrowRight, Boxes, FileCheck2, PackageCheck, ShieldCheck } from "lucide-react";
import Image from "next/image";
import { notFound } from "next/navigation";
import { ArchitectureFlowDemo } from "@/components/landing/architecture-flow-demo";
import { AuditLifecycle } from "@/components/landing/audit-lifecycle";
import { isSiteLocale } from "@/lib/i18n";
import { gitConfig } from "@/lib/shared";
import styles from "@/components/landing/landing.module.css";

const issuesUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}/issues`;
const designUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}/tree/${gitConfig.branch}/docs/design`;

const copy = {
  "zh-CN": {
    title: "给 Agent 测评一条可复现的外层边界",
    summary:
      "BORA（Bounded Orchestration for Runtime Agents）锁定 Dataset 配置、按边界跑 Attempt、控制 agent 可见面，再由独立 evaluator 出分。Coding agent 统一走 ACP，轨迹可审计，但轨迹永远不等于 PASS。",
    primary: "入门",
    secondary: "编写 Task",
    console: {
      label: "本机公开路径",
      run: "bora lock → bora run → bora view",
      status: "lock · run · evidence",
      steps: [
        ["01", "load_and_lock", "Database + task 规格锁定"],
        ["02", "Attempt", "Harness × ACP × 可见性投影"],
        ["03", "Evaluator", "独立 barrier · 唯一 PASS 权威"],
        ["04", "Evidence", "轨迹落盘 · bora view / export"],
      ],
    },
    platform: {
      eyebrow: "Authority-first runtime",
      title: "Harness 写业务 loop，Core 守运行边界",
      summary:
        "package 拥有 workflow、角色与本地 Tool；BORA Core 拥有 lock、Attempt 生命周期、Provider 隔离、Capability、硬顶与 evaluator barrier。第三方 Agent SDK 不得成为 PASS 或 identity 权威。",
      items: [
        [
          "01",
          "Dataset · Task package",
          "根 bora.yaml 描述 suite；tasks/*/task.yaml 描述 harness、profiles、limits 与 evaluator。",
          PackageCheck,
        ],
        [
          "02",
          "Locked Attempt",
          "正式运行只消费 lock 快照；参数与 envelope 分离，禁止 harness 再读第二份真配置。",
          Boxes,
        ],
        [
          "03",
          "Visibility & ceilings",
          "路径 / secret / network 靠投影强制；硬顶在 effect 前执行，事后 usage 只作观测。",
          ShieldCheck,
        ],
        [
          "04",
          "Independent evaluation",
          "Harness completed ≠ PASS。PASS 只来自独立 evaluator 与 Core 绑定后的结果。",
          FileCheck2,
        ],
      ],
    },
    graph: {
      eyebrow: "Architecture paths",
      title: "三条路径，一个权威边界",
    },
    foundations: {
      eyebrow: "Product surfaces",
      title: "运行 · 查看结果 · 可选归档",
      items: [
        [
          "CLI",
          "lock / run / campaign / evidence",
          "公开入口以 bora --help 为准；suite 可并发，PASS 仍 per-task。",
        ],
        [
          "VIEWER",
          "本机 Jobs → Tasks → Attempt",
          "bora view 浏览 .bora/suite-runs/ 与轨迹；不连 Registry。",
        ],
        [
          "HUB",
          "Registry Dataset 目录",
          "浏览包、README、Leaderboard 与 Jobs 列表；与本机 viewer 职责分离。",
        ],
        [
          "DOCS",
          "设计在 docs/ · 用法在站内",
          "本站是读者向重写；机制权威在仓库 docs/design，交付跟踪在 GitHub Issues。",
        ],
      ],
    },
    audit: {
      eyebrow: "Sealed facts",
      title: "从 invoke 到 evaluation 的事实链",
    },
    cta: {
      eyebrow: "Issues + docs",
      title: "增量交付在 Issues，机制细节在 docs/design",
      primary: "打开文档",
      secondary: "GitHub Issues",
    },
  },
  en: {
    title: "An outer boundary for reproducible agent evaluation",
    summary:
      "BORA (Bounded Orchestration for Runtime Agents) locks Dataset config, runs bounded Attempts, projects visibility, and lets an independent evaluator own the score. Coding agents enter via ACP. Trajectories are auditable — and never PASS.",
    primary: "Get started",
    secondary: "Authoring",
    console: {
      label: "Local public path",
      run: "bora lock → bora run → bora view",
      status: "lock · run · evidence",
      steps: [
        ["01", "load_and_lock", "Dataset + task snapshot"],
        ["02", "Attempt", "Harness × ACP × visibility"],
        ["03", "Evaluator", "Independent barrier · PASS authority"],
        ["04", "Evidence", "On-disk trajectory · view / export"],
      ],
    },
    platform: {
      eyebrow: "Authority-first runtime",
      title: "Harness owns the loop. Core owns the boundary.",
      summary:
        "Packages own workflow, roles, and local tools. BORA Core owns lock, Attempt lifecycle, Provider isolation, Capability, hard ceilings, and the evaluator barrier. Third-party agent SDKs must not become PASS or identity authority.",
      items: [
        [
          "01",
          "Dataset · Task package",
          "Root bora.yaml describes the suite; tasks/*/task.yaml describes harness, profiles, limits, and evaluator.",
          PackageCheck,
        ],
        [
          "02",
          "Locked Attempt",
          "Formal runs consume only the lock snapshot. Parameters and envelope stay separate; harness must not re-read a second truth.",
          Boxes,
        ],
        [
          "03",
          "Visibility & ceilings",
          "Paths, secrets, and network are projected. Hard ceilings reject before effect; post-hoc usage is observation only.",
          ShieldCheck,
        ],
        [
          "04",
          "Independent evaluation",
          "Harness completed ≠ PASS. Only an independent evaluator plus Core binding may form PASS.",
          FileCheck2,
        ],
      ],
    },
    graph: {
      eyebrow: "Architecture paths",
      title: "Three paths, one authority boundary",
    },
    foundations: {
      eyebrow: "Product surfaces",
      title: "Run · inspect · optionally archive",
      items: [
        [
          "CLI",
          "lock / run / campaign / evidence",
          "Public entrypoints follow bora --help. Suites may run concurrently; PASS stays per-task.",
        ],
        [
          "VIEWER",
          "Local Jobs → Tasks → Attempt",
          "bora view browses .bora/suite-runs/ and trajectories without Registry.",
        ],
        [
          "HUB",
          "Registry Dataset catalog",
          "Browse packages, README, Leaderboard, and job lists — separate from the local viewer.",
        ],
        [
          "DOCS",
          "Design in docs/ · how-to on this site",
          "This site is reader-facing. Mechanism truth lives in docs/design; delivery tracks on GitHub Issues.",
        ],
      ],
    },
    audit: {
      eyebrow: "Sealed facts",
      title: "Fact chain from invoke to evaluation",
    },
    cta: {
      eyebrow: "Issues + docs",
      title: "Ship work via Issues; keep mechanism detail in docs/design",
      primary: "Open docs",
      secondary: "GitHub Issues",
    },
  },
} as const;

export default async function HomePage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isSiteLocale(lang)) notFound();
  const text = copy[lang];

  return (
    <main className={styles.landing}>
      <section className={styles.heroBand}>
        <div className={styles.heroGrid}>
          <div className={styles.heroCopy}>
            <Image
              className={styles.brandIllustration}
              src="/images/bora-hero.png"
              alt="BORA runtime boundary and evaluation"
              width={1536}
              height={1024}
              priority
              unoptimized
            />
            <h1>{text.title}</h1>
            <p className={styles.heroSummary}>{text.summary}</p>
            <div className={styles.heroActions}>
              <Link className={styles.primaryActionOnDark} href={`/${lang}/docs/getting-started/install`}>
                {text.primary}
                <ArrowRight aria-hidden="true" />
              </Link>
              <Link className={styles.ghostActionOnDark} href={`/${lang}/docs/author/tutorial`}>
                {text.secondary}
              </Link>
            </div>
          </div>

          <div className={styles.heroRunPanel} aria-label={text.console.label}>
            <div className={styles.heroRunHeader}>
              <span>{text.console.label}</span>
              <strong>{text.console.status}</strong>
            </div>
            <p className={styles.heroRunName}>{text.console.run}</p>
            <ol className={styles.heroRunSteps}>
              {text.console.steps.map(([number, label, status], index) => (
                <li key={label} data-current={index === 0}>
                  <span>{number}</span>
                  <strong>{label}</strong>
                  <small>{status}</small>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      <section className={styles.platformBand}>
        <div className={styles.sectionHeader}>
          <p className={styles.monoEyebrow}>{text.platform.eyebrow}</p>
          <h2>{text.platform.title}</h2>
          <p>{text.platform.summary}</p>
        </div>
        <div className={styles.capabilityRows}>
          {text.platform.items.map(([number, title, body, Icon]) => (
            <article key={number} className={styles.capabilityRow}>
              <span className={styles.capabilityNumber}>{number}</span>
              <Icon aria-hidden="true" />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.graphBand}>
        <div className={styles.sectionHeaderCompact}>
          <p className={styles.monoEyebrow}>{text.graph.eyebrow}</p>
          <h2>{text.graph.title}</h2>
        </div>
        <ArchitectureFlowDemo lang={lang} />
      </section>

      <section className={styles.foundationBand}>
        <div className={styles.sectionHeaderOnDark}>
          <p className={styles.monoEyebrow}>{text.foundations.eyebrow}</p>
          <h2>{text.foundations.title}</h2>
        </div>
        <div className={styles.foundationGrid}>
          {text.foundations.items.map(([label, title, body]) => (
            <article key={label} className={styles.foundationCard}>
              <p>{label}</p>
              <h3>{title}</h3>
              <span>{body}</span>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.auditBand}>
        <div className={styles.sectionHeaderCompact}>
          <p className={styles.monoEyebrow}>{text.audit.eyebrow}</p>
          <h2>{text.audit.title}</h2>
        </div>
        <AuditLifecycle lang={lang} />
      </section>

      <section className={styles.ctaBand}>
        <div>
          <p className={styles.monoEyebrow}>{text.cta.eyebrow}</p>
          <h2>{text.cta.title}</h2>
        </div>
        <div className={styles.ctaActions}>
          <Link className={styles.primaryAction} href={`/${lang}/docs/getting-started/first-run`}>
            {text.cta.primary}
            <ArrowRight aria-hidden="true" />
          </Link>
          <Link className={styles.secondaryAction} href={issuesUrl}>
            {text.cta.secondary}
          </Link>
        </div>
        <p className="mt-4 text-sm opacity-70">
          <a href={designUrl}>docs/design</a>
        </p>
      </section>
    </main>
  );
}
