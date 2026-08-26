"use client";

/**
 * Canvas 2D digitile of the owl face mark.
 *
 * Same construction as DeepSeek Harness HeroDigitileR3F, without three.js:
 * rasterize the evenodd face path onto a coarse grid, drop isolated specks,
 * draw a square per cell. Pointer in the host (hero or nav logo) pushes
 * nearby tiles with cubic falloff. After assemble, the whole mark
 * breathes one shared opacity envelope (DeepSeek shimmer period) and
 * a slight group bob / rotation plus edge drift (uLoose).
 */

import { useEffect, useRef } from "react";
import { OWL_FACE_PATH, OWL_FACE_SIZE } from "@/components/owl-flat";

type OwlPixelProps = {
  className?: string;
};

type Cell = {
  gx: number;
  gy: number;
  opacity: number;
  edge: number;
  size: number;
  seed: number;
  scatterX: number;
  scatterY: number;
};

type VariantConfig = {
  grid: number;
  host: string;
  assembleMs: number;
  assembleDelayMs: number;
  mouseRadius: number;
  mouseStrength: number;
  tileFill: number;
  fps: number;
};

const HERO: VariantConfig = {
  grid: 52,
  host: ".hero",
  assembleMs: 1400,
  assembleDelayMs: 280,
  mouseRadius: 0.42,
  mouseStrength: 0.9,
  tileFill: 0.58,
  fps: 30,
};

/** Shared opacity envelope after assemble. Peak is 80% of the old full-bright. */
const BREATH_MIN = 0.35;
const BREATH_MAX = 0.8;

function hash01(i: number, salt: number): number {
  const x = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

function rasterizeFace(grid: number): Cell[] {
  const canvas = document.createElement("canvas");
  canvas.width = grid;
  canvas.height = grid;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return [];

  ctx.fillStyle = "rgb(0, 0, 0)";
  ctx.fillRect(0, 0, grid, grid);

  const pad = 1;
  const avail = grid - pad * 2;
  const scale = Math.min(avail / OWL_FACE_SIZE.width, avail / OWL_FACE_SIZE.height);
  const drawnW = OWL_FACE_SIZE.width * scale;
  const drawnH = OWL_FACE_SIZE.height * scale;
  const ox = (grid - drawnW) / 2;
  const oy = (grid - drawnH) / 2;
  ctx.setTransform(scale, 0, 0, scale, ox, oy);
  ctx.fillStyle = "rgb(255, 255, 255)";
  ctx.fill(new Path2D(OWL_FACE_PATH), "evenodd");
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  const { data } = ctx.getImageData(0, 0, grid, grid);
  const lum = new Float32Array(grid * grid);
  for (let i = 0; i < lum.length; i++) {
    const o = i * 4;
    lum[i] = (0.299 * data[o] + 0.587 * data[o + 1] + 0.114 * data[o + 2]) / 255;
  }

  const isolated = (x: number, y: number) => {
    for (let dy = -2; dy <= 2; dy++) {
      for (let dx = -2; dx <= 2; dx++) {
        if (dx === 0 && dy === 0) continue;
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= grid || ny >= grid) continue;
        if (lum[ny * grid + nx] > 0.2) return false;
      }
    }
    return true;
  };

  const cells: Cell[] = [];
  for (let y = 0; y < grid; y++) {
    for (let x = 0; x < grid; x++) {
      const a = lum[y * grid + x];
      if (a <= 0.2 || isolated(x, y)) continue;
      let edge = 0;
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          if (dx === 0 && dy === 0) continue;
          const nx = x + dx;
          const ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= grid || ny >= grid || lum[ny * grid + nx] <= 0.2) {
            edge += 1;
          }
        }
      }
      const i = cells.length;
      const angle = hash01(i, 1) * Math.PI * 2;
      const radius = 0.35 + 0.65 * hash01(i, 2);
      cells.push({
        gx: x,
        gy: y,
        opacity: a,
        edge: edge / 8,
        size: 0.55 + 0.7 * hash01(i, 3),
        seed: i + 1,
        scatterX: Math.cos(angle) * radius,
        scatterY: Math.sin(angle) * radius,
      });
    }
  }
  return cells;
}

function prefersReduce(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function hasHoverPointer(): boolean {
  return window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

export function OwlPixelMark({ className }: OwlPixelProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const cfg = HERO;
    const cells = rasterizeFace(cfg.grid);
    if (cells.length === 0) return;

    const reduced = prefersReduce();
    const hoverOk = hasHoverPointer() && !reduced;
    const host = (wrap.closest(cfg.host) as HTMLElement | null) ?? wrap;

    let cssW = 0;
    let cssH = 0;
    let dpr = 1;
    let color = "currentColor";
    let raf = 0;
    let running = false;
    let lastDraw = 0;
    let onScreen = true;
    const frameMs = 1000 / cfg.fps;
    const start = performance.now();

    const mouse = { x: 0.5, y: 0.5, sx: 0.5, sy: 0.5, active: false, strength: 0 };
    const cellPx = { w: 1, h: 1 };

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
      cellPx.w = cssW / cfg.grid;
      cellPx.h = cssH / cfg.grid;
      color = getComputedStyle(wrap).color || color;
    };

    const assembly = (now: number) => {
      if (reduced || cfg.assembleMs <= 0) return 1;
      const t = (now - start - cfg.assembleDelayMs) / cfg.assembleMs;
      const u = Math.max(0, Math.min(1, t));
      return 1 - (1 - u) ** 3;
    };

    const paint = (now: number) => {
      resize();
      if (cssW < 2 || cssH < 2) return true;
      const assembled = assembly(now);
      const radius = Math.min(cssW, cssH) * cfg.mouseRadius;
      mouse.sx += (mouse.x - mouse.sx) * 0.22;
      mouse.sy += (mouse.y - mouse.sy) * 0.22;
      const targetStrength = mouse.active && hoverOk ? cfg.mouseStrength : 0;
      mouse.strength += (targetStrength - mouse.strength) * 0.18;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, cssW, cssH);

      const idle = reduced ? 0 : assembled >= 1 ? 1 : Math.max(0, (assembled - 0.9) / 0.1);
      const sec = now / 1000;
      const wave = 0.5 - 0.5 * Math.cos((sec * Math.PI * 2) / 6);
      const idleBreath = BREATH_MIN + (BREATH_MAX - BREATH_MIN) * wave;
      const breath = (1 - idle) * BREATH_MAX + idle * idleBreath;
      ctx.translate(
        cssW / 2 + idle * Math.sin(sec * 0.25) * cssW * 0.008,
        cssH / 2 + idle * Math.sin(sec * 0.4) * cssH * 0.022,
      );
      ctx.rotate(idle * Math.sin(sec * 0.25) * 0.04);
      ctx.translate(-cssW / 2, -cssH / 2);
      ctx.fillStyle = color;

      const mx = mouse.sx * cssW;
      const my = mouse.sy * cssH;
      const lightX = cssW * 0.28;
      const lightY = cssH * 0.22;
      const lightRange = Math.hypot(cssW, cssH) * 0.72;

      for (const cell of cells) {
        const restX = (cell.gx + 0.5) * cellPx.w;
        const restY = (cell.gy + 0.5) * cellPx.h;
        const fromX = restX + cell.scatterX * cssW;
        const fromY = restY + cell.scatterY * cssH;
        let x = fromX + (restX - fromX) * assembled;
        let y = fromY + (restY - fromY) * assembled;

        if (idle > 0) {
          const loose = (0.25 + 0.75 * cell.edge) * idle;
          x += Math.sin(sec * 0.5 + cell.seed * 0.53) * cellPx.w * 0.22 * loose;
          y += Math.cos(sec * 0.42 + cell.seed * 0.71) * cellPx.h * 0.22 * loose;
        }

        if (mouse.strength > 0.01 && assembled > 0.8) {
          const dx = x - mx;
          const dy = y - my;
          const dist = Math.hypot(dx, dy);
          if (dist < radius && dist > 0.001) {
            const t = 1 - dist / radius;
            const force = t * t * t * mouse.strength * (0.8 + 0.4 * cell.edge);
            const noise = Math.sin(cell.seed * 0.37) * 0.7;
            const ca = Math.cos(noise);
            const sa = Math.sin(noise);
            const ux = dx / dist;
            const uy = dy / dist;
            const px = ux * ca - uy * sa;
            const py = ux * sa + uy * ca;
            const mouseEffect = (assembled - 0.8) * 5;
            x += px * force * mouseEffect * radius * 0.35;
            y += py * force * mouseEffect * radius * 0.35;
          }
        }

        const lit = Math.max(0, 1 - Math.hypot(x - lightX, y - lightY) / lightRange);
        const shade = 0.55 + 0.7 * lit * lit;
        const tile = Math.min(cellPx.w, cellPx.h) * cfg.tileFill * cell.size;
        ctx.globalAlpha =
          cell.opacity * (0.42 + 0.38 * assembled) * Math.min(shade, 1) * breath;
        ctx.fillRect(x - tile / 2, y - tile / 2, tile, tile);
      }
      ctx.globalAlpha = 1;

      return !reduced && onScreen && !document.hidden;
    };

    const tick = (now: number) => {
      if (now - lastDraw < frameMs) {
        raf = requestAnimationFrame(tick);
        return;
      }
      lastDraw = now;
      const keep = paint(now);
      if (keep) {
        raf = requestAnimationFrame(tick);
        return;
      }
      running = false;
      raf = 0;
    };

    const kick = () => {
      if (running) return;
      running = true;
      lastDraw = 0;
      raf = requestAnimationFrame(tick);
    };

    const onMove = (event: PointerEvent) => {
      if (!hoverOk) return;
      const box = wrap.getBoundingClientRect();
      if (box.width <= 0 || box.height <= 0) return;
      mouse.x = (event.clientX - box.left) / box.width;
      mouse.y = (event.clientY - box.top) / box.height;
      mouse.active = true;
      kick();
    };

    const onLeave = () => {
      mouse.active = false;
      kick();
    };

    const onVisibility = () => {
      if (document.hidden) {
        mouse.active = false;
        running = false;
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
        return;
      }
      if (reduced) {
        paint(performance.now());
        return;
      }
      kick();
    };

    resize();
    if (reduced) {
      paint(start + 10_000);
    } else {
      kick();
    }

    const ro = new ResizeObserver(() => {
      resize();
      if (!running) paint(performance.now());
    });
    ro.observe(wrap);

    const io = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen) {
          if (reduced) paint(performance.now());
          else kick();
        } else {
          running = false;
          if (raf) cancelAnimationFrame(raf);
          raf = 0;
        }
      },
      { rootMargin: "80px" },
    );
    io.observe(wrap);

    host.addEventListener("pointermove", onMove, { passive: true });
    host.addEventListener("pointerleave", onLeave);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      running = false;
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      className={className}
      aria-hidden="true"
      data-owl-pixel="hero"
    >
      <canvas ref={canvasRef} />
    </div>
  );
}
