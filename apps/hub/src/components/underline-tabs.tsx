import { useLayoutEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

type Item<T extends string> = { id: T; label: string };

export function UnderlineTabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  size = "md",
  className,
}: {
  items: readonly Item<T>[];
  value: T;
  onChange: (id: T) => void;
  ariaLabel: string;
  size?: "md" | "sm";
  className?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [bar, setBar] = useState({ x: 0, w: 0 });

  useLayoutEffect(() => {
    const root = listRef.current;
    if (!root) return;
    const btn = root.querySelector<HTMLElement>(
      `[data-tab-id="${CSS.escape(value)}"]`,
    );
    if (!btn) return;

    const measure = () => {
      setBar({ x: btn.offsetLeft, w: btn.offsetWidth });
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
      className={cn("relative flex flex-wrap gap-1 border-b border-hairline", className)}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          data-tab-id={item.id}
          aria-selected={value === item.id}
          onClick={() => onChange(item.id)}
          className={cn(
            "relative z-10 font-mono text-xs uppercase tracking-wide",
            "transition-colors duration-200 ease-smooth",
            size === "sm" ? "px-2.5 py-1.5" : "px-3 py-2",
            value === item.id
              ? "font-semibold text-ink"
              : "text-mute hover:text-body",
          )}
        >
          {item.label}
        </button>
      ))}
      <span
        aria-hidden
        className="pointer-events-none absolute bottom-0 left-0 h-0.5 bg-link motion-safe:transition-[transform,width] motion-safe:duration-200 motion-safe:ease-smooth"
        style={{ width: bar.w, transform: `translateX(${bar.x}px)` }}
      />
    </div>
  );
}
