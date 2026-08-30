"use client";

import { useEffect, useState } from "react";
import { HARNESSES, type Harness } from "./harness-marks";

const INTERVAL_MS = 2600;
const CROSSFADE_MS = 400;

function HarnessLine({ harness }: { harness: Harness }) {
  return (
    <>
      {"src" in harness ? (
        <span
          className={harness.tone === "ink" ? "hero-rotate-plate" : "hero-rotate-icon"}
        >
          <img
            src={harness.src}
            alt=""
            width={24}
            height={24}
            draggable={false}
            className="hero-rotate-mark"
          />
        </span>
      ) : (
        <span className="hero-rotate-icon">
          <harness.Mark className="hero-rotate-mark" />
        </span>
      )}
      <span className="hero-rotate-name">{harness.name}</span>
    </>
  );
}

type RotateState = {
  index: number;
  prev: number | null;
  /** Bumps on every swap so both layers remount and their CSS animations restart. */
  tick: number;
};

/**
 * True crossfade: on every swap both layers mount as fresh nodes — the
 * outgoing one fades out in place while the incoming one fades in on a
 * stacked overlay, so the two overlap with no blank gap. With reduced
 * motion the first entry stays static.
 */
export function HeroRotate() {
  const [state, setState] = useState<RotateState>({ index: 0, prev: null, tick: 0 });

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      setState(({ index, tick }) => ({
        index: (index + 1) % HARNESSES.length,
        prev: index,
        tick: tick + 1,
      }));
    }, INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (state.prev === null) return;
    const timer = window.setTimeout(() => {
      setState(({ index, tick }) => ({ index, prev: null, tick }));
    }, CROSSFADE_MS);
    return () => window.clearTimeout(timer);
  }, [state.prev]);

  const active = HARNESSES[state.index];
  const outgoing = state.prev === null ? null : HARNESSES[state.prev];

  return (
    <span className="hero-rotate">
      {outgoing && (
        <span
          className="hero-rotate-layer is-leaving"
          key={`out-${state.tick}`}
          aria-hidden="true"
        >
          <HarnessLine harness={outgoing} />
        </span>
      )}
      <span
        className="hero-rotate-layer is-active"
        key={`in-${active.id}-${state.tick}`}
      >
        <HarnessLine harness={active} />
      </span>
    </span>
  );
}
