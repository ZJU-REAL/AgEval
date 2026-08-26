"use client";

import { useEffect, useRef } from "react";

/**
 * ThreeUI `signal-particles` field, drawn locally.
 *
 * The npm `PredictiveArcCanvas` variant bakes `speed: 1` into an iframe
 * srcDoc and only tries to override it with a postMessage that often
 * misses. Speed here multiplies the original `time += 0.02` step:
 * `1` = ThreeUI default, `0.1` = 10× slower, `0.01` = 100× slower.
 */

const SPEED = 0.3;
const HUE = -8;
const SATURATION = 0.4;
const BRIGHTNESS = 0.5;
const SPACING = 16;
const DOT_RADIUS = 1.5;
const BASE_STEP = 0.02;

export function HeroSignal() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cssW = 0;
    let cssH = 0;
    let dpr = 1;
    let raf = 0;
    let running = false;
    let onScreen = true;
    let time = 0;
    let last = 0;

    const resize = () => {
      const nextDpr = Math.min(window.devicePixelRatio || 1, 2);
      const nextW = Math.max(1, wrap.clientWidth);
      const nextH = Math.max(1, wrap.clientHeight);
      if (nextW === cssW && nextH === cssH && nextDpr === dpr) return;
      cssW = nextW;
      cssH = nextH;
      dpr = nextDpr;
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      canvas.style.width = `${cssW}px`;
      canvas.style.height = `${cssH}px`;
    };

    const paint = (now: number) => {
      resize();
      if (cssW < 2 || cssH < 2) return;
      const dt = last === 0 ? 1 : Math.min(2.5, (now - last) / 16.67);
      last = now;
      time += BASE_STEP * SPEED * dt;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      const cols = Math.floor(cssW / SPACING);
      const rows = Math.floor(cssH / SPACING);
      const offsetX = (cssW - cols * SPACING) / 2;
      const offsetY = (cssH - rows * SPACING) / 2;

      for (let i = 0; i <= cols; i++) {
        for (let j = 0; j <= rows; j++) {
          const nx = i * 0.1;
          const ny = j * 0.1;
          const wave1 = Math.sin(nx + time * 0.5) * Math.cos(ny - time * 0.3);
          const wave2 = Math.sin(nx * 0.5 - ny * 0.5 + time * 0.8);
          const value = wave1 + wave2;
          if (value <= 0.1) continue;

          const x = offsetX + i * SPACING;
          const y = offsetY + j * SPACING;
          const highlight = Math.sin(i * 12.34) * Math.cos(j * 56.78);
          if (highlight > 0.98) {
            ctx.fillStyle = "rgb(59, 130, 246)";
          } else if (highlight < -0.98) {
            ctx.fillStyle = "rgb(139, 92, 246)";
          } else {
            const alpha = Math.min(0.6, (value - 0.1) * 0.8);
            ctx.fillStyle = `rgba(148, 163, 184, ${alpha})`;
          }
          ctx.beginPath();
          ctx.arc(x, y, DOT_RADIUS, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };

    const tick = (now: number) => {
      if (!running) return;
      paint(now);
      raf = requestAnimationFrame(tick);
    };

    const start = () => {
      if (running) return;
      running = true;
      last = 0;
      raf = requestAnimationFrame(tick);
    };

    const stop = () => {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };

    const ro = new ResizeObserver(() => {
      resize();
      if (!running) paint(performance.now());
    });
    ro.observe(wrap);

    const io = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen && !document.hidden) start();
        else stop();
      },
      { rootMargin: "80px" },
    );
    io.observe(wrap);

    const onVisibility = () => {
      if (document.hidden) stop();
      else if (onScreen) start();
    };
    document.addEventListener("visibilitychange", onVisibility);

    resize();
    start();

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className="hero-signal"
      aria-hidden="true"
      style={{
        filter: `hue-rotate(${HUE}deg) saturate(${SATURATION}) brightness(${BRIGHTNESS})`,
      }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
