import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DshWhale } from "@/components/landing/dsh-whale";
import { landingCopy } from "@/components/landing/copy";
import { LandingNav } from "@/components/landing/landing-nav";
import { OwlFlatMark } from "@/components/owl-flat";
import { isSiteLocale } from "@/lib/i18n";
import { gitConfig } from "@/lib/shared";

const repoUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}`;
const designUrl = `https://github.com/${gitConfig.user}/${gitConfig.repo}/tree/${gitConfig.branch}/docs/design`;

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
    <div className="bora-landing">
      <a className="skip" href="#main">
        {text.skip}
      </a>

      <LandingNav lang={lang} copy={text.nav} navAria={text.navAria} repoUrl={repoUrl} />

      <main id="main">
        <section className="hero" id="top">
          <div className="hero-grid" aria-hidden="true" />
          <OwlFlatMark className="owl-wash" />
          <div className="wrap-wide hero-layout">
            <div>
              <h1 className="hero-brand">
                {text.hero.brand}
                <span>.</span>
              </h1>
              <p className="hero-sub">
                {text.hero.title[0]}
                <br />
                {text.hero.title[1]}
              </p>
              <p className="hero-lead">{text.hero.lead}</p>
              <div className="hero-ctas">
                <a className="btn btn-pri" href={repoUrl} rel="noopener noreferrer">
                  {text.hero.primary}
                </a>
                <a className="btn btn-ghost" href={`/${lang}/docs`}>
                  {text.hero.secondary}
                </a>
              </div>
            </div>
            <aside className="stage" aria-label={text.hero.stageAria}>
              <span className="cross tl" aria-hidden="true" />
              <span className="cross br" aria-hidden="true" />
              <p className="stage-head">
                <b>{text.hero.stagePkg}</b>
                <span>{text.hero.stagePhase}</span>
              </p>
              <ol className="inspect">
                {text.hero.rows.map(([key, value, note]) => (
                  <li key={key}>
                    <p className="k">{key}</p>
                    <div>
                      <strong>{value}</strong>
                      <span>{note}</span>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="stage-foot">
                {text.hero.foot} <code>{text.hero.help}</code> {text.hero.footAfter}
                <code>{text.hero.footCmd}</code>
              </p>
            </aside>
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
                <article key={lv}>
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
                  {"  "}
                  <span className="ck">chain:</span>
                  {"\n"}
                  {"    "}- <span className="ck">id:</span> trajectory_collect
                </pre>
                <pre className="code-panel mini" tabIndex={0}>
                  <span className="cc"># plugins/dsh/src/dsh_plugin/factory.py</span>
                  {"\n"}
                  <span className="ck">DEFAULT_MODEL</span> = <span className="cs">&quot;deepseek-v4-flash&quot;</span>
                  {"\n\n"}
                  <span className="ck">def</span> build_executor(**kwargs) -&gt; DshExecutorSPI:{"\n"}
                  {"    "}
                  <span className="ck">return</span> DshExecutorSPI(**kwargs){"\n\n"}
                  <span className="ck">class</span> DshExecutorSPI:{"\n"}
                  {"    "}kind = <span className="cs">&quot;dsh&quot;</span>
                  {"\n"}
                  {"    "}
                  <span className="ck">def</span> bind_to_target(self, placement):{"\n"}
                  {"        "}
                  <span className="cc"># bind into the box Core already opened</span>
                  {"\n"}
                  {"        "}
                  <span className="ck">return</span> DshContainerExecutor(...)
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
            <div className="hero-ctas">
              <a className="btn btn-pri" href={repoUrl} rel="noopener noreferrer">
                {text.cta.primary}
              </a>
              <a className="btn btn-ghost" href={`/${lang}/docs`}>
                {text.cta.docs}
              </a>
            </div>
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
                <article key={question} className="faq-item" tabIndex={0}>
                  <p className="faq-q">{question}</p>
                  <div className="faq-a">{answer}</div>
                </article>
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
