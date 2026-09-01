import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { BookOpen, Orbit } from "lucide-react";
import { DshWhale } from "@/components/landing/dsh-whale";
import { landingCopy } from "@/components/landing/copy";
import { LandingNav } from "@/components/landing/landing-nav";
import { HeroSignal } from "@/components/landing/hero-signal";
import { HeroRotate } from "@/components/landing/hero-rotate";
import { OwlPixelMark } from "@/components/landing/owl-pixel";
import { StartCode } from "@/components/landing/start-code";
import { isSiteLocale } from "@/lib/i18n";
import { gitConfig, hubSiteUrl } from "@/lib/shared";

/** GitHub invertocat. Fill uses currentColor. Path matches hub `GitHubIcon`. */
function GitHubMark() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 1 100 97.53"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M50 1C22.39 1 0 23.386 0 51c0 22.092 14.326 40.835 34.193 47.446 2.499.463 3.416-1.085 3.416-2.405 0-1.192-.046-5.132-.067-9.31-13.91 3.025-16.846-5.899-16.846-5.899-2.274-5.78-5.552-7.316-5.552-7.316-4.536-3.103.342-3.04.342-3.04 5.021.353 7.665 5.153 7.665 5.153 4.46 7.644 11.697 5.434 14.55 4.157.449-3.232 1.745-5.437 3.175-6.686-11.106-1.265-22.78-5.552-22.78-24.71 0-5.46 1.953-9.92 5.151-13.421-.519-1.26-2.23-6.345.485-13.232 0 0 4.198-1.344 13.753 5.125 3.988-1.108 8.266-1.663 12.515-1.682 4.25.018 8.53.574 12.526 1.682 9.543-6.47 13.736-5.125 13.736-5.125 2.722 6.887 1.01 11.972.49 13.232 3.206 3.501 5.146 7.961 5.146 13.42 0 19.204-11.697 23.433-22.83 24.67 1.793 1.553 3.39 4.596 3.39 9.26 0 6.69-.057 12.075-.057 13.722 0 1.33.9 2.89 3.434 2.398C85.691 91.82 100 73.085 100 51.001c0-27.615-22.386-50-50-50" />
    </svg>
  );
}

const repoUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;
const designUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}/tree/${gitConfig.branch}/docs/design`;
const hubUrl = hubSiteUrl();

function HeroCtas({
  repoLabel,
  hubLabel,
  docsLabel,
  docsHref,
}: {
  repoLabel: string;
  hubLabel: string;
  docsLabel: string;
  docsHref: string;
}) {
  return (
    <div className="hero-ctas">
      <a className="btn btn-pri" href={repoUrl} rel="noopener noreferrer">
        <GitHubMark />
        {repoLabel}
      </a>
      {hubUrl ? (
        <a className="btn btn-ghost" href={hubUrl} rel="noopener noreferrer">
          <Orbit aria-hidden="true" />
          {hubLabel}
        </a>
      ) : null}
      <a className="btn btn-ghost" href={docsHref}>
        <BookOpen aria-hidden="true" />
        {docsLabel}
      </a>
    </div>
  );
}


function HeroTitleB({ line, accent }: { line: string; accent: string }) {
  const i = line.indexOf(accent);
  if (i < 0) return line;
  return (
    <>
      {line.slice(0, i)}
      <span className="hero-title-accent">{accent}</span>
      {line.slice(i + accent.length)}
    </>
  );
}

type HomeParams = { lang: string };

export async function generateMetadata({
  params,
}: {
  params: Promise<HomeParams>;
}): Promise<Metadata> {
  const { lang } = await params;
  if (!isSiteLocale(lang)) return {};
  const text = landingCopy[lang];
  return {
    title: { absolute: text.metaTitle },
    description: text.metaDescription,
  };
}

export default async function HomePage({ params }: { params: Promise<HomeParams> }) {
  const { lang } = await params;
  if (!isSiteLocale(lang)) notFound();
  const text = landingCopy[lang];

  return (
    <div className="ageval-landing">
      <a className="skip" href="#main">
        {text.skip}
      </a>

      <LandingNav lang={lang} copy={text.nav} navAria={text.navAria} repoUrl={repoUrl} />

      <main id="main">
        <section className="hero" id="top">
          <HeroSignal />
          <div className="hero-grid" aria-hidden="true" />
          <OwlPixelMark className="owl-wash" />
          <div className="wrap-wide hero-stack">
            <div className="hero-center">
              <h1 className="hero-title">
                <span className="hero-title-a">{text.hero.titleA}</span>
                <span className="hero-title-b">
                  <HeroTitleB line={text.hero.titleB} accent={lang === "en" ? "anywhere" : "到处"} />
                </span>
                <HeroRotate />
              </h1>
              <p className="hero-note">{text.hero.note}</p>
              <HeroCtas
                repoLabel={text.hero.primary}
                hubLabel={text.hero.hub}
                docsLabel={text.hero.secondary}
                docsHref={`/${lang}/docs`}
              />
            </div>
            <div className="hero-foot">
              <aside className="stage" aria-label={text.hero.startAria}>
                <span className="cross tl" aria-hidden="true" />
                <span className="cross br" aria-hidden="true" />
                <StartCode
                  label={text.hero.startLabel}
                  copyLabel={text.hero.copy}
                  copiedLabel={text.hero.copied}
                />
              </aside>
            </div>
          </div>
        </section>

        <section className="pact" aria-label={text.pactAria}>
          <div className="wrap pact-inner">
            {text.pact.map(([en, zh, body]) => (
              <article key={en}>
                <p className="en">{en}</p>
                <p className="zh">{zh}</p>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="block" id="problem">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.problem.index}</span>
              <span className="sec-name">{text.problem.name}</span>
            </div>
            <h2>
              {text.problem.title[0]}
              <br />
              {text.problem.title[1]}
            </h2>
            <div className="problem-grid">
              {text.problem.items.map(([k, title, body]) => (
                <article key={k}>
                  <p className="k">{k}</p>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
            <p className="sol">
              {text.problem.solLabel} <b>{text.problem.sol}</b>
            </p>
          </div>
        </section>

        <section className="block" id="position">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.position.index}</span>
              <span className="sec-name">{text.position.name}</span>
            </div>
            <h2>{text.position.title}</h2>
            <p className="lead">{text.position.lead}</p>
            <div className="split">
              <div className="owned">
                <h3>{text.position.ownedLabel}</h3>
                <p>{text.position.owned}</p>
                <small>{text.position.ownedNote}</small>
              </div>
              <div className="not">
                <h3>{text.position.notLabel}</h3>
                <p>{text.position.not}</p>
                <small>{text.position.notNote}</small>
              </div>
            </div>
          </div>
        </section>

        <section className="block" id="principles">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.principles.index}</span>
              <span className="sec-name">{text.principles.name}</span>
            </div>
            <h2>{text.principles.title}</h2>
            <ol className="principles">
              {text.principles.items.map(([title, body]) => (
                <li key={title}>
                  <strong>{title}</strong>
                  <p>{body}</p>
                </li>
              ))}
            </ol>
            <div className="ink-banner">
              <div className="en">
                {text.principles.bannerEn[0]}
                <br />
                {text.principles.bannerEn[1]}
                <br />
                {text.principles.bannerEn[2]}
              </div>
              <p className="zh">{text.principles.bannerZh}</p>
            </div>
          </div>
        </section>

        <section className="block" id="core">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.core.index}</span>
              <span className="sec-name">{text.core.name}</span>
            </div>
            <h2>{text.core.title}</h2>
            <p className="lead">{text.core.lead}</p>
            <div className="core-grid">
              {text.core.items.map(([id, title, body, own, hot]) => (
                <article key={id} className={hot ? "hot" : undefined}>
                  <span className="id">{id}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  <p className="own">{own}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="block" id="isolation">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.isolation.index}</span>
              <span className="sec-name">{text.isolation.name}</span>
            </div>
            <h2>{text.isolation.title}</h2>
            <p className="lead">{text.isolation.lead}</p>
            <div className="tiers">
              {text.isolation.items.map(([st, title, body, tag, hot]) => (
                <article key={st} className={hot ? "hot" : undefined}>
                  <p className="st">{st}</p>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  <p className="tag">{tag}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="block" id="eval">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.eval.index}</span>
              <span className="sec-name">{text.eval.name}</span>
            </div>
            <h2>{text.eval.title}</h2>
            <div className="barrier">
              <div>
                <p className="lead">{text.eval.lead}</p>
                <p className="ne" aria-hidden="true">
                  {text.eval.neLeft} <span>≠</span> {text.eval.neRight}
                </p>
              </div>
              <dl className="barrier-note">
                {text.eval.steps.map(([dt, dd]) => (
                  <div key={dt}>
                    <dt>{dt}</dt>
                    <dd>{dd}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </section>

        <section className="block" id="plugin">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.plugin.index}</span>
              <span className="sec-name">{text.plugin.name}</span>
            </div>
            <h2>{text.plugin.title}</h2>
            <p className="lead">{text.plugin.lead}</p>
            <div className="slots">
              {text.plugin.slots.map(([lv, title, body]) => (
                <article key={title}>
                  <div className="lv">{lv}</div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="block" id="plugin-code">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.pluginCode.index}</span>
              <span className="sec-name">{text.pluginCode.name}</span>
            </div>
            <h2>{text.pluginCode.title}</h2>
            <p className="lead">{text.pluginCode.lead}</p>
            <div className="duo">
              <div className="duo-col">
                <p className="duo-tag">
                  <span className="num">01</span> {text.pluginCode.coreTag}
                </p>
                <pre className="code-panel" tabIndex={0}>
                  <span className="cc"># src/ageval/plugins/slots.py</span>
                  {"\n"}
                  <span className="ck">class</span> SlotKind(StrEnum):{"\n"}
                  {"    "}CHAIN = <span className="cs">&quot;chain&quot;</span>
                  {"      "}
                  <span className="cc"># (ctx, value, nxt)</span>
                  {"\n"}
                  {"    "}EXCLUSIVE = <span className="cs">&quot;exclusive&quot;</span>
                  {"  "}
                  <span className="cc"># 一个赢家</span>
                  {"\n\n"}
                  ENVIRONMENT: Final = <span className="cs">&quot;environment&quot;</span>
                  {"\n"}
                  EXECUTOR: Final = <span className="cs">&quot;executor&quot;</span>
                  {"\n\n"}
                  <span className="cc"># src/ageval/environments/protocol.py</span>
                  {"\n"}
                  <span className="ck">class</span> ExecutorSPI(Protocol):{"\n"}
                  {"    "}kind: str{"\n"}
                  {"    "}
                  <span className="ck">def</span> invoke(self, prompt, *, timeout=60.0,{"\n"}
                  {"               "}workdir=None, collect_dir=None) -&gt; Any: ...{"\n"}
                  {"    "}
                  <span className="ck">def</span> close(self) -&gt; None: ...{"\n\n"}
                  HookHandler = Callable[[Any, Any, NextFn], Awaitable[Any]]
                </pre>
                <p className="code-note">{text.pluginCode.note}</p>
              </div>
              <div className="duo-col accent">
                <DshWhale />
                <p className="duo-tag">
                  <span className="num">02</span> {text.pluginCode.pluginTag}
                </p>
                <pre className="code-panel" tabIndex={0}>
                  <span className="cc"># plugins/dsh/plugin.yaml</span>
                  {"\n"}
                  <span className="ck">format:</span> ageval.plugin/1{"\n"}
                  <span className="ck">plugin_id:</span> dsh{"\n"}
                  <span className="ck">host_requires:</span>
                  {"\n"}
                  {"  "}- <span className="ck">import:</span> deepseek_harness{"\n"}
                  <span className="ck">slots:</span>
                  {"\n"}
                  {"  "}
                  <span className="ck">exclusive:</span>
                  {"\n"}
                  {"    "}- <span className="ck">id:</span> executor{"\n"}
                  {"      "}
                  <span className="ck">entry:</span> <span className="cs">&quot;dsh_plugin.factory:build_executor&quot;</span>
                  {"\n"}
                  <span className="ck">inject:</span>
                  {"\n"}
                  {"  "}- <span className="ck">service:</span> environment{"\n"}
                  {"    "}
                  <span className="ck">capabilities:</span> [exec, upload]
                </pre>
                <pre className="code-panel mini" tabIndex={0}>
                  <span className="cc"># plugins/dsh — parent never imports the harness</span>
                  {"\n"}
                  <span className="ck">def</span> build_executor(*, host, placement, **kw) -&gt; DshBoxExecutor:{"\n"}
                  {"    "}
                  <span className="ck">return</span> DshBoxExecutor(host=host, placement=placement, **kw)
                  {"\n\n"}
                  <span className="ck">await</span> host.upload(worker, <span className="cs">&quot;/attempt/home/_dsh/…&quot;</span>){"\n"}
                  <span className="ck">await</span> host.exec([*host.python_command, worker, request], env=creds)
                </pre>
              </div>
            </div>
          </div>
        </section>

        <section className="block" id="flow">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.flow.index}</span>
              <span className="sec-name">{text.flow.name}</span>
            </div>
            <h2>{text.flow.title}</h2>
            <ol className="flow">
              {text.flow.steps.map(([n, title, body]) => (
                <li key={n}>
                  <span className="n">{n}</span>
                  <strong>{title}</strong>
                  <span>{body}</span>
                </li>
              ))}
            </ol>
            <div className="traj">
              {text.flow.traj.map(([title, body]) => (
                <article key={title}>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="take">
          <div className="take-left">
            <div>
              <p className="hero-tag">{text.take.tag}</p>
              <h2>{text.take.title}</h2>
            </div>
            <p>{text.take.body}</p>
          </div>
          <div className="take-right">
            <ol>
              {text.take.items.map(([num, title, body]) => (
                <li key={num}>
                  <div className="num">{num}</div>
                  <div>
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="cta-band">
          <div className="wrap">
            <h2>
              {text.cta.title[0]}
              <br />
              {text.cta.title[1]}
            </h2>
            <p className="lead">{text.cta.lead}</p>
            <HeroCtas
              repoLabel={text.cta.primary}
              hubLabel={text.cta.hub}
              docsLabel={text.cta.docs}
              docsHref={`/${lang}/docs`}
            />
          </div>
        </section>

        <section className="block" id="faq">
          <div className="wrap">
            <div className="sec-head">
              <span className="sec-index">{text.faq.index}</span>
              <span className="sec-name">{text.faq.name}</span>
            </div>
            <h2>{text.faq.title}</h2>
            <div className="faq-list">
              {text.faq.items.map(([question, answer]) => (
                <details key={question} className="faq-item">
                  <summary className="faq-q">{question}</summary>
                  <div className="faq-panel">
                    <div className="faq-a">{answer}</div>
                  </div>
                </details>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap foot">
          <div>
            <a className="logo" href="#top">
              ageval<span>.</span>
            </a>
            <p>{text.footer.body}</p>
          </div>
          <small>
            <a href={designUrl}>{text.footer.mark}</a>
          </small>
        </div>
      </footer>
    </div>
  );
}
