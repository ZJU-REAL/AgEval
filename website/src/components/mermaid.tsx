"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTheme } from "next-themes";
import { Maximize2, RotateCcw, X, ZoomIn, ZoomOut } from "lucide-react";

type RenderedDiagram = {
  svg: string;
  bindFunctions?: (element: Element) => void;
};

const MIN_SCALE = 0.25;
const MAX_SCALE = 4;
const SCALE_STEP = 0.25;

const mermaidModule = import("mermaid");

/**
 * Renders trusted, repository-owned Mermaid source in the browser.
 *
 * The initial empty state is shared by server rendering and hydration. The
 * effect then imports Mermaid and renders with the active light or dark theme.
 * Theme changes replace the SVG without changing the MDX source contract.
 * Clicking a diagram opens it in a fullscreen lightbox with zoom controls so
 * complex sequence and flow diagrams stay readable on small viewports.
 */
export function Mermaid({ chart }: { chart: string }) {
  const id = useId().replaceAll(":", "-");
  const { resolvedTheme } = useTheme();
  const [diagram, setDiagram] = useState<RenderedDiagram>();
  const [renderError, setRenderError] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const normalizedChart = chart.replaceAll("\\n", "\n");

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      try {
        const { default: mermaid } = await mermaidModule;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          fontFamily: "inherit",
          theme: resolvedTheme === "dark" ? "dark" : "neutral",
        });

        const rendered = await mermaid.render(id, normalizedChart);
        if (!cancelled) {
          setDiagram(rendered);
          setRenderError(false);
        }
      } catch {
        if (!cancelled) setRenderError(true);
      }
    }

    void renderDiagram();
    return () => {
      cancelled = true;
    };
  }, [id, normalizedChart, resolvedTheme]);

  const close = useCallback(() => {
    setIsOpen(false);
    setScale(1);
  }, []);

  const zoomIn = useCallback(() => setScale((value) => Math.min(MAX_SCALE, value + SCALE_STEP)), []);
  const zoomOut = useCallback(
    () => setScale((value) => Math.max(MIN_SCALE, value - SCALE_STEP)),
    [],
  );

  if (renderError) {
    return (
      <pre className="my-6 overflow-x-auto rounded-xl border bg-fd-card p-4 text-sm">
        <code>{normalizedChart}</code>
      </pre>
    );
  }
  if (!diagram) return <div className="my-6 h-28 animate-pulse rounded-xl border bg-fd-muted" />;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-label="放大查看此图"
        title="点击放大查看"
        className="group relative my-6 block w-full cursor-zoom-in overflow-x-auto rounded-xl border bg-fd-card p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fd-ring [&_svg]:mx-auto [&_svg]:max-w-full"
        ref={(element) => {
          if (element) diagram.bindFunctions?.(element);
        }}
        dangerouslySetInnerHTML={{ __html: diagram.svg }}
      />
      {isOpen ? (
        <DiagramLightbox
          svg={diagram.svg}
          scale={scale}
          onClose={close}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onReset={() => setScale(1)}
        />
      ) : null}
    </>
  );
}

type DiagramLightboxProps = {
  svg: string;
  scale: number;
  onClose: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
};

function DiagramLightbox({
  svg,
  scale,
  onClose,
  onZoomIn,
  onZoomOut,
  onReset,
}: DiagramLightboxProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "+" || event.key === "=") {
        event.preventDefault();
        onZoomIn();
      } else if (event.key === "-" || event.key === "_") {
        event.preventDefault();
        onZoomOut();
      } else if (event.key === "0") {
        event.preventDefault();
        onReset();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    closeButtonRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose, onZoomIn, onZoomOut, onReset]);

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="放大查看图"
      className="fixed inset-0 z-50 flex flex-col bg-fd-overlay backdrop-blur-sm"
    >
      <div className="flex items-center justify-between gap-2 border-b border-fd-border bg-fd-card px-3 py-2">
        <div className="flex items-center gap-1">
          <LightboxButton label="缩小" onClick={onZoomOut} disabled={scale <= MIN_SCALE}>
            <ZoomOut className="size-4" />
          </LightboxButton>
          <span
            aria-live="polite"
            className="min-w-[3.5rem] text-center font-mono text-xs text-fd-muted-foreground"
          >
            {Math.round(scale * 100)}%
          </span>
          <LightboxButton label="放大" onClick={onZoomIn} disabled={scale >= MAX_SCALE}>
            <ZoomIn className="size-4" />
          </LightboxButton>
          <LightboxButton label="重置缩放" onClick={onReset} disabled={scale === 1}>
            <RotateCcw className="size-4" />
          </LightboxButton>
        </div>
        <LightboxButton label="关闭" onClick={onClose}>
          <X className="size-4" />
        </LightboxButton>
      </div>
      <div
        className="relative flex-1 overflow-auto"
        onClick={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <div
          className="flex min-h-full min-w-full p-6"
          onClick={(event) => {
            if (event.target === event.currentTarget) onClose();
          }}
        >
          <div
            className="m-auto shrink-0 rounded-[14px] border border-fd-border bg-fd-card p-4 shadow-[var(--viewer-shadow-pop)] [&_svg]:h-auto [&_svg]:max-w-none [&_svg]:w-full"
            style={{ width: `${100 * scale}%`, maxWidth: "none" }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-fd-border bg-fd-card px-3 py-1 text-center font-mono text-[0.65rem] text-fd-muted-foreground">
        <Maximize2 className="mr-1 inline size-3 align-text-bottom" />
        滚动查看 · Esc 关闭 · +/- 缩放
      </div>
    </div>,
    document.body,
  );
}

function LightboxButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="inline-flex size-8 items-center justify-center rounded-md border border-transparent text-fd-muted-foreground transition hover:bg-fd-accent hover:text-fd-accent-foreground disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fd-ring"
    >
      {children}
    </button>
  );
}
