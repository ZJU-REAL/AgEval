"use client";

import { useId, useState, type ReactNode } from "react";
import type { LandingCopy } from "./copy";

type FlowCopy = LandingCopy["position"]["flow"];

const COLS = [
  { x: 0, w: 160 },
  { x: 160, w: 160 },
  { x: 320, w: 160 },
  { x: 480, w: 160 },
  { x: 640, w: 160 },
  { x: 800, w: 164 },
] as const;
const COL_W = 160;
const HIT_Y = 4;
const HIT_H = 468;

function colClass(i: number, step: number): string {
  if (i === step) return "is-active";
  if (i < step) return "is-passed";
  return "is-upcoming";
}

function Badge({
  x,
  y,
  label,
  accent = false,
}: {
  x: number;
  y: number;
  label: string;
  accent?: boolean;
}) {
  const w = label.length > 3 ? 26 : 22;
  return (
    <>
      <rect
        className={accent ? "core-flow-badge is-accent" : "core-flow-badge"}
        x={x}
        y={y}
        width={w}
        height={12}
        rx={2}
      />
      <text className="core-flow-badge-t" x={x + w / 2} y={y + 9}>
        {label}
      </text>
    </>
  );
}

function IconFrame({
  x,
  y,
  accent = false,
  children,
}: {
  x: number;
  y: number;
  accent?: boolean;
  children: ReactNode;
}) {
  return (
    <svg
      x={x}
      y={y}
      width={24}
      height={24}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={accent ? "core-flow-icon is-accent" : "core-flow-icon"}
    >
      {children}
    </svg>
  );
}

function Chip({
  x,
  y,
  viewBox,
  children,
}: {
  x: number;
  y: number;
  viewBox: string;
  children: ReactNode;
}) {
  return (
    <svg x={x} y={y} width={16} height={16} viewBox={viewBox} aria-hidden="true" className="core-flow-chip">
      {children}
    </svg>
  );
}

export function CoreFlow({ copy }: { copy: FlowCopy }) {
  const uid = useId().replace(/:/g, "");
  const [step, setStep] = useState(0);

  const dots = `${uid}-dots`;
  const arrow = `${uid}-arrow`;
  const arrowAccent = `${uid}-arrow-accent`;
  const arrowSm = `${uid}-arrow-sm`;
  const titleId = `${uid}-title`;
  const descId = `${uid}-desc`;
  const noteId = `${uid}-note`;
  const note = copy.notes[step] ?? copy.notes[0];

  return (
    <div className="core-flow-block">
    <figure
      className="core-flow"
      data-step={step}
      aria-label={copy.aria}
    >
      <div className="core-flow-scroll">
        <div className="core-flow-canvas">
        <svg
          className="core-flow-svg"
          viewBox="0 0 1000 540"
          role="img"
          aria-labelledby={`${titleId} ${descId}`}
          aria-describedby={noteId}
        >
          <title id={titleId}>{copy.svgTitle}</title>
          <desc id={descId}>{copy.svgDesc}</desc>
          <defs>
            <pattern id={dots} width={22} height={22} patternUnits="userSpaceOnUse">
              <circle cx={1} cy={1} r={0.9} className="core-flow-dot" />
            </pattern>
            <marker id={arrow} markerWidth={8} markerHeight={6} refX={7} refY={3} orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="context-stroke" />
            </marker>
            <marker id={arrowAccent} markerWidth={8} markerHeight={6} refX={7} refY={3} orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="context-stroke" />
            </marker>
            <marker id={arrowSm} markerWidth={6} markerHeight={5} refX={5} refY={2.5} orient="auto">
              <polygon points="0 0, 6 2.5, 0 5" fill="context-stroke" />
            </marker>
          </defs>

          <rect width="100%" height="100%" className="core-flow-bg" />
          <rect width="100%" height="100%" fill={`url(#${dots})`} opacity={0.55} />

          <rect className="core-flow-zone is-dash" x={4} y={40} width={152} height={336} rx={6} />
          <rect className="core-flow-zone" x={164} y={40} width={800} height={336} rx={8} />
          <rect className="core-flow-bar" x={4} y={388} width={960} height={40} rx={6} />
          <rect className="core-flow-bar" x={4} y={432} width={960} height={40} rx={6} />

          <rect
            className="core-flow-beam"
            x={0}
            y={4}
            width={COL_W}
            height={464}
            rx={8}
            style={{ transform: `translateX(${step * 100}%)` }}
          />

          <g
            className={`core-flow-col ${colClass(0, step)}`}
          >
            <polygon className="core-flow-chevron" points="0,4 148,4 160,18 148,32 0,32" />
            <text className="core-flow-chevron-t" x={80} y={21}>
              INPUTS
            </text>
            <text className="core-flow-zone-t" x={80} y={52}>
              INPUTS
            </text>
          </g>
          <g
            className={`core-flow-col ${colClass(1, step)}`}
          >
            <polygon className="core-flow-chevron" points="160,4 308,4 320,18 308,32 160,32 172,18" />
            <text className="core-flow-chevron-t" x={240} y={21}>
              LOCK
            </text>
          </g>
          <g
            className={`core-flow-col ${colClass(2, step)}`}
          >
            <polygon className="core-flow-chevron" points="320,4 468,4 480,18 468,32 320,32 332,18" />
            <text className="core-flow-chevron-t" x={400} y={21}>
              ENVIRONMENT
            </text>
          </g>
          <g
            className={`core-flow-col ${colClass(3, step)}`}
          >
            <polygon className="core-flow-chevron" points="480,4 628,4 640,18 628,32 480,32 492,18" />
            <text className="core-flow-chevron-t" x={560} y={21}>
              RUN
            </text>
          </g>
          <g
            className={`core-flow-col ${colClass(4, step)}`}
          >
            <polygon className="core-flow-chevron" points="640,4 788,4 800,18 788,32 640,32 652,18" />
            <text className="core-flow-chevron-t" x={720} y={21}>
              EVALUATE
            </text>
          </g>
          <g
            className={`core-flow-col ${colClass(5, step)}`}
          >
            <polygon className="core-flow-chevron" points="800,4 964,4 964,32 800,32 812,18" />
            <text className="core-flow-chevron-t" x={882} y={21}>
              RECORD
            </text>
          </g>

          <g className={`core-flow-span${step >= 1 ? " is-on" : ""}`}>
            <polygon className="core-flow-chevron" points="972,40 1000,40 1000,244 986,256 972,244" />
            <text className="core-flow-chevron-t" x={986} y={148} transform="rotate(-90 986 148)">
              LIMITS
            </text>
            <polygon className="core-flow-chevron is-alt" points="972,256 986,268 1000,256 1000,472 972,472" />
            <text className="core-flow-chevron-t" x={986} y={364} transform="rotate(-90 986 364)">
              CLEANUP
            </text>
          </g>

          <g className={`core-flow-col ${colClass(0, step)}`}>
            <path
              className={`core-flow-edge${step <= 1 ? " is-live" : ""}`}
              d="M 152,128 H 156 Q 160,128 160,132 V 108 Q 160,104 164,104 H 170"
              markerEnd={`url(#${arrow})`}
            />
            <path
              className={`core-flow-edge${step <= 1 ? " is-live" : ""}`}
              d="M 152,208 H 156 Q 160,208 160,204 V 140 Q 160,136 164,136 H 170"
              markerEnd={`url(#${arrow})`}
            />
            <path
              className={`core-flow-edge${step <= 1 ? " is-live" : ""}`}
              d="M 152,288 H 156 Q 160,288 160,284 V 172 Q 160,168 164,168 H 170"
              markerEnd={`url(#${arrow})`}
            />
          </g>
          <line
            className={`core-flow-edge${step >= 1 ? " is-live" : ""}`}
            x1={310}
            y1={136}
            x2={330}
            y2={136}
            markerEnd={`url(#${arrow})`}
          />
          <line
            className={`core-flow-edge${step >= 2 ? " is-live" : ""}`}
            x1={470}
            y1={136}
            x2={490}
            y2={136}
            markerEnd={`url(#${arrow})`}
          />
          <line
            className={`core-flow-edge${step >= 3 ? " is-live" : ""}`}
            x1={630}
            y1={136}
            x2={650}
            y2={136}
            markerEnd={`url(#${arrow})`}
          />
          <line
            className={`core-flow-edge is-accent${step >= 4 ? " is-live" : ""}`}
            x1={790}
            y1={136}
            x2={810}
            y2={136}
            markerEnd={`url(#${arrowAccent})`}
          />
          <line
            className={`core-flow-edge is-dash${step === 1 ? " is-live" : ""}`}
            x1={240}
            y1={176}
            x2={240}
            y2={208}
            markerEnd={`url(#${arrowSm})`}
          />
          <line
            className={`core-flow-edge is-dash${step === 2 ? " is-live" : ""}`}
            x1={400}
            y1={176}
            x2={400}
            y2={208}
            markerEnd={`url(#${arrowSm})`}
          />
          <line
            className={`core-flow-edge is-dash${step === 3 ? " is-live" : ""}`}
            x1={560}
            y1={176}
            x2={560}
            y2={208}
            markerEnd={`url(#${arrowSm})`}
          />

          <g
            className={`core-flow-col ${colClass(0, step)}`}
          >
            <rect className="core-flow-card" x={8} y={96} width={144} height={64} rx={6} />
            <Badge x={16} y={102} label="EXT" />
            <IconFrame x={68} y={102}>
              <circle cx={12} cy={8} r={4} />
              <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6" />
            </IconFrame>
            <text className="core-flow-name" x={80} y={138}>
              {copy.user}
            </text>
            <text className="core-flow-meta" x={80} y={150}>
              {copy.userMeta}
            </text>

            <rect className="core-flow-card" x={8} y={176} width={144} height={64} rx={6} />
            <Badge x={16} y={182} label="EXT" />
            <IconFrame x={68} y={182}>
              <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
              <path d="M14 3v6h6" />
            </IconFrame>
            <text className="core-flow-name" x={80} y={218}>
              {copy.dataset}
            </text>
            <text className="core-flow-meta" x={80} y={230}>
              {copy.datasetMeta}
            </text>

            <rect className="core-flow-card" x={8} y={256} width={144} height={64} rx={6} />
            <Badge x={16} y={262} label="EXT" />
            <IconFrame x={68} y={262}>
              <line x1={4} y1={7} x2={20} y2={7} />
              <line x1={4} y1={12} x2={20} y2={12} />
              <line x1={4} y1={17} x2={20} y2={17} />
              <circle cx={9} cy={7} r={2} />
              <circle cx={15} cy={12} r={2} />
              <circle cx={7} cy={17} r={2} />
            </IconFrame>
            <text className="core-flow-name" x={80} y={298}>
              {copy.profiles}
            </text>
            <text className="core-flow-meta" x={80} y={310}>
              {copy.profilesMeta}
            </text>
          </g>

          <g
            className={`core-flow-col ${colClass(1, step)}`}
          >
            <rect className="core-flow-card" x={170} y={96} width={140} height={80} rx={6} />
            <Badge x={178} y={102} label="CLI" />
            <IconFrame x={228} y={104}>
              <rect x={3} y={4} width={18} height={16} rx={2} />
              <polyline points="7,9 10,12 7,15" />
              <line x1={12} y1={15} x2={17} y2={15} />
            </IconFrame>
            <text className="core-flow-name" x={240} y={148}>
              {copy.lock}
            </text>
            <text className="core-flow-meta" x={240} y={162}>
              {copy.lockMeta}
            </text>
            <rect className="core-flow-plugin" x={170} y={208} width={140} height={80} rx={6} />
            <text className="core-flow-plugin-t" x={240} y={226}>
              {copy.pluginBind}
            </text>
            <text className="core-flow-meta" x={240} y={265}>
              {copy.pluginBindMeta}
            </text>
            <text className="core-flow-meta" x={240} y={279}>
              {copy.pluginBindNote}
            </text>
          </g>

          <g
            className={`core-flow-col ${colClass(2, step)}`}
          >
            <rect className="core-flow-card" x={330} y={96} width={140} height={80} rx={6} />
            <Badge x={338} y={102} label="PROV" />
            <IconFrame x={388} y={104}>
              <path d="M12 2l8 4.5v9L12 20l-8-4.5v-9z" />
              <path d="M12 11L4 6.5M12 11l8-4.5M12 11v9" />
            </IconFrame>
            <text className="core-flow-name" x={400} y={148}>
              {copy.environment}
            </text>
            <text className="core-flow-meta" x={400} y={162}>
              {copy.environmentMeta}
            </text>
            <rect className="core-flow-plugin" x={330} y={208} width={140} height={80} rx={6} />
            <text className="core-flow-plugin-t" x={400} y={226}>
              {copy.envPlugins}
            </text>
            <Chip x={353} y={231} viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M13.983 11.078h2.119a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.119a.185.185 0 00-.185.185v1.888c0 .102.083.185.185.185m-2.954-5.43h2.118a.186.186 0 00.186-.186V3.574a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m0 2.716h2.118a.187.187 0 00.186-.186V6.29a.186.186 0 00-.186-.185h-2.118a.185.185 0 00-.185.185v1.887c0 .102.082.185.185.186m-2.93 0h2.12a.186.186 0 00.184-.186V6.29a.185.185 0 00-.185-.185H8.1a.185.185 0 00-.185.185v1.887c0 .102.083.185.185.186m-2.964 0h2.119a.186.186 0 00.185-.186V6.29a.185.185 0 00-.185-.185H5.136a.186.186 0 00-.186.185v1.887c0 .102.084.185.186.186m5.893 2.715h2.118a.186.186 0 00.186-.185V9.006a.186.186 0 00-.186-.186h-2.118a.185.185 0 00-.185.185v1.888c0 .102.082.185.185.185m-2.93 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.083.185.185.185m-2.964 0h2.119a.185.185 0 00.185-.185V9.006a.185.185 0 00-.184-.186h-2.12a.186.186 0 00-.186.186v1.887c0 .102.084.185.186.185m-2.92 0h2.12a.185.185 0 00.184-.185V9.006a.185.185 0 00-.184-.186h-2.12a.185.185 0 00-.184.185v1.888c0 .102.082.185.185.185M23.763 9.89c-.065-.051-.672-.51-1.954-.51-.338.001-.676.03-1.01.087-.248-1.7-1.653-2.53-1.716-2.566l-.344-.199-.226.327c-.284.438-.49.922-.612 1.43-.23.97-.09 1.882.403 2.661-.595.332-1.55.413-1.744.42H.751a.751.751 0 00-.75.748 11.376 11.376 0 00.692 4.062c.545 1.428 1.355 2.48 2.41 3.124 1.18.723 3.1 1.137 5.275 1.137.983.003 1.963-.086 2.93-.266a12.248 12.248 0 003.823-1.389c.98-.567 1.86-1.288 2.61-2.136 1.252-1.418 1.998-2.997 2.553-4.4h.221c1.372 0 2.215-.549 2.68-1.009.309-.293.55-.65.707-1.046l.098-.288Z"
              />
            </Chip>
            <Chip x={379} y={231} viewBox="0 0 20.4 18">
              <path
                fill="currentColor"
                d="M20.2235 0V4.67645H5.49328C5.04263 4.67661 4.67645 5.0426 4.67645 5.49328V5.84494C4.67645 6.29563 5.04263 6.66161 5.49328 6.66178H20.2235V11.3382H5.49328C5.04263 11.3384 4.67645 11.7044 4.67645 12.1551V12.5067C4.67657 12.9573 5.04271 13.3222 5.49328 13.3223H20.2235V18H3.12668C1.39998 17.9996 1.98414e-05 16.5989 0 14.8721V3.12668C0.000280465 1.40008 1.40013 0.000432767 3.12668 0H20.2235Z"
              />
            </Chip>
            <Chip x={405} y={231} viewBox="0 0 275 287">
              <path fill="currentColor" d="M14.5584 193.736H114.275V227.925H14.5584V193.736Z" />
              <path fill="currentColor" d="M148.464 74.076H262.426V108.265H148.464V74.076Z" />
              <path fill="currentColor" d="M88.6338 84.6127L173.246 0L197.422 24.175L112.809 108.788L88.6338 84.6127Z" />
              <path fill="currentColor" d="M89.157 170.084L24.175 105.102L0 129.277L64.9819 194.259L89.157 170.084Z" />
              <path fill="currentColor" d="M174.629 217.911L106.133 286.407L81.9577 262.232L150.454 193.736L174.629 217.911Z" />
              <path fill="currentColor" d="M174.106 132.44L250.66 208.994L274.835 184.819L198.281 108.265L174.106 132.44Z" />
              <path fill="currentColor" d="M88.6338 48.434V131.057H54.4451L54.4451 48.434H88.6338Z" />
              <path fill="currentColor" d="M208.294 168.094V270.66H174.106V168.094H208.294Z" />
            </Chip>
            <Chip x={431} y={231} viewBox="0 0 24 24">
              <rect x={3} y={4} width={18} height={16} rx={2} fill="none" stroke="currentColor" strokeWidth={1.8} />
              <polyline points="7,9 10,12 7,15" fill="none" stroke="currentColor" strokeWidth={1.8} />
              <line x1={12} y1={15} x2={17} y2={15} stroke="currentColor" strokeWidth={1.8} />
            </Chip>
            <text className="core-flow-meta" x={400} y={265}>
              {copy.envPluginsMeta}
            </text>
            <text className="core-flow-meta" x={400} y={279}>
              {copy.envPluginsNote}
            </text>
          </g>

          <g
            className={`core-flow-col ${colClass(3, step)}`}
          >
            <rect className="core-flow-card" x={490} y={96} width={140} height={80} rx={6} />
            <Badge x={498} y={102} label="TASK" />
            <IconFrame x={548} y={104}>
              <circle cx={12} cy={12} r={9} />
              <polygon points="10,8.5 16,12 10,15.5" fill="currentColor" stroke="none" />
            </IconFrame>
            <text className="core-flow-name" x={560} y={148}>
              {copy.run}
            </text>
            <text className="core-flow-meta" x={560} y={162}>
              {copy.runMeta}
            </text>
            <rect className="core-flow-plugin" x={490} y={208} width={140} height={80} rx={6} />
            <text className="core-flow-plugin-t" x={560} y={226}>
              {copy.agentPlugins}
            </text>
            <Chip x={507} y={231} viewBox="0 0 24 24">
              <path fill="currentColor" fillRule="evenodd" d="M1 1h16.5v11H12v5.5H6.5V23H1V1zm5.5 5.5V12H12V6.5H6.5z" />
              <path fill="currentColor" d="M17.5 12H23v11h-5.5V12z" />
            </Chip>
            <Chip x={537} y={231} viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M19.503 0H4.496A4.496 4.496 0 000 4.496v15.007A4.496 4.496 0 004.496 24h15.007A4.496 4.496 0 0024 19.503V4.496A4.496 4.496 0 0019.503 0z"
              />
            </Chip>
            <Chip x={567} y={231} viewBox="0 0 24 24">
              <path
                fill="currentColor"
                fillRule="evenodd"
                d="M20.998 10.949H24v3.102h-3v3.028h-1.487V20H18v-2.921h-1.487V20H15v-2.921H9V20H7.488v-2.921H6V20H4.487v-2.921H3V14.05H0V10.95h3V5h17.998v5.949zM6 10.949h1.488V8.102H6v2.847zm10.51 0H18V8.102h-1.49v2.847z"
              />
            </Chip>
            <Chip x={597} y={231} viewBox="0 0 24 24">
              <path fill="currentColor" fillRule="evenodd" d="M16 6H8v12h8V6zm4 16H4V2h16v20z" />
            </Chip>
            <text className="core-flow-meta" x={560} y={265}>
              {copy.agentPluginsMeta}
            </text>
            <text className="core-flow-meta" x={560} y={279}>
              {copy.agentPluginsNote}
            </text>
          </g>

          <g
            className={`core-flow-col ${colClass(4, step)}`}
          >
            <rect className="core-flow-card" x={650} y={96} width={140} height={80} rx={6} />
            <Badge x={658} y={102} label="EVAL" />
            <IconFrame x={708} y={104}>
              <circle cx={12} cy={12} r={9} />
              <polyline points="8,12.5 11,15.5 16,9.5" />
            </IconFrame>
            <text className="core-flow-name" x={720} y={148}>
              {copy.evaluate}
            </text>
            <text className="core-flow-meta" x={720} y={162}>
              {copy.evaluateMeta}
            </text>
          </g>

          <g
            className={`core-flow-col ${colClass(5, step)}`}
          >
            <rect className="core-flow-card is-focal" x={810} y={96} width={140} height={80} rx={8} />
            <Badge x={818} y={102} label="EVID" accent />
            <IconFrame x={870} y={104} accent>
              <ellipse cx={12} cy={5.5} rx={8} ry={3} />
              <path d="M4 5.5v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
              <path d="M4 11.5v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" />
            </IconFrame>
            <text className="core-flow-name is-accent" x={882} y={148}>
              {copy.evidence}
            </text>
            <text className="core-flow-meta is-accent" x={882} y={162}>
              {copy.evidenceMeta}
            </text>
          </g>

          <g className="core-flow-note">
            <IconFrame x={180} y={348}>
              <path d="M12 2l8 4.5v9L12 20l-8-4.5v-9z" />
              <path d="M12 11L4 6.5M12 11l8-4.5M12 11v9" />
            </IconFrame>
            <text className="core-flow-note-t" x={204} y={362}>
              {copy.coreNote}
            </text>
          </g>

          <g className={`core-flow-span${step >= 1 ? " is-on" : ""}`}>
            <IconFrame x={348} y={398}>
              <path d="M12 3a9 9 0 0 1 9 9" />
              <path d="M12 3a9 9 0 0 0-9 9" />
              <line x1={12} y1={12} x2={16} y2={8} />
              <circle cx={12} cy={12} r={1.5} fill="currentColor" stroke="none" />
            </IconFrame>
            <text className="core-flow-name" x={484} y={410}>
              {copy.limits}
            </text>
            <text className="core-flow-meta" x={484} y={422}>
              {copy.limitsMeta}
            </text>
          </g>

          <g className={`core-flow-span${step >= 1 ? " is-on" : ""}`}>
            <IconFrame x={352} y={442}>
              <path d="M20 12a8 8 0 1 1-2.34-5.66" />
              <polyline points="20,3 20,7 16,7" />
            </IconFrame>
            <text className="core-flow-name" x={484} y={454}>
              {copy.cleanup}
            </text>
            <text className="core-flow-meta" x={484} y={466}>
              {copy.cleanupMeta}
            </text>
          </g>

          <g className="core-flow-legend">
            <line className="core-flow-legend-rule" x1={40} y1={496} x2={952} y2={496} />
            <text className="core-flow-legend-k" x={40} y={512}>
              {copy.legend}
            </text>
            <rect className="core-flow-plugin" x={40} y={520} width={20} height={12} rx={3} />
            <text className="core-flow-legend-t" x={68} y={530}>
              {copy.legendExt}
            </text>
            <rect className="core-flow-card" x={228} y={520} width={20} height={12} rx={3} />
            <text className="core-flow-legend-t" x={256} y={530}>
              {copy.legendCore}
            </text>
            <rect className="core-flow-card is-focal" x={416} y={520} width={20} height={12} rx={3} />
            <text className="core-flow-legend-t" x={444} y={530}>
              {copy.legendEvidence}
            </text>
            <line
              className="core-flow-edge is-accent is-live"
              x1={560}
              y1={522}
              x2={580}
              y2={522}
              markerEnd={`url(#${arrowAccent})`}
            />
            <text className="core-flow-legend-t" x={588} y={527}>
              {copy.legendPass}
            </text>
            <line
              className="core-flow-edge is-live"
              x1={688}
              y1={522}
              x2={708}
              y2={522}
              markerEnd={`url(#${arrow})`}
            />
            <text className="core-flow-legend-t" x={716} y={527}>
              {copy.legendPhase}
            </text>
            <rect className="core-flow-plugin" x={820} y={520} width={20} height={12} rx={3} />
            <text className="core-flow-legend-t" x={848} y={530}>
              {copy.legendPlugin}
            </text>
          </g>

          {COLS.map((c, i) => (
            <rect
              key={c.x}
              className="core-flow-hit"
              x={c.x}
              y={HIT_Y}
              width={c.w}
              height={HIT_H}
              onPointerEnter={() => setStep(i)}
            />
          ))}
        </svg>
        </div>
      </div>
    </figure>
    <p className="core-flow-caption" id={noteId}>
      <span className="core-flow-caption-k">{`// ${note[0]}`}</span>{" "}
      {note[1]}
    </p>
    </div>
  );
}
