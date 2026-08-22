import { useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Item<T extends string> = { id: T; label: string };

export function PillTabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  className,
}: {
  items: readonly Item<T>[];
  value: T;
  onChange: (id: T) => void;
  ariaLabel: string;
  className?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [bar, setBar] = useState({ x: 0, y: 0, w: 0, h: 0 });
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    const root = listRef.current;
    if (!root) return;
    const btn = root.querySelector<HTMLElement>(
      `[data-tab-id="${CSS.escape(value)}"]`,
    );
    if (!btn) return;

    const measure = () => {
      setBar({
        x: btn.offsetLeft,
        y: btn.offsetTop,
        w: btn.offsetWidth,
        h: btn.offsetHeight,
      });
      setReady(true);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    ro.observe(btn);
    return () => ro.disconnect();
  }, [value, items]);

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "relative inline-flex shrink-0 rounded-[6px] border border-hairline bg-canvas p-0.5",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute top-0 left-0 rounded-[4px] bg-canvas-soft",
          ready &&
            "motion-safe:transition-[transform,width,height] motion-safe:duration-[400ms] motion-safe:ease-glide",
        )}
        style={{
          width: bar.w,
          height: bar.h,
          transform: `translate(${bar.x}px, ${bar.y}px)`,
        }}
      />
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          data-tab-id={item.id}
          aria-selected={value === item.id}
          onClick={() => onChange(item.id)}
          className={cn(
            "relative z-10 rounded-[4px] px-2 py-0.5 text-[11px]",
            "transition-colors duration-200 ease-smooth",
            value === item.id
              ? "font-medium text-ink"
              : "text-mute hover:text-ink",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
