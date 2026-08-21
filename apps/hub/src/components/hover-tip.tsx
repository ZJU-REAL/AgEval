import {
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export function HoverTip({
  content,
  children,
  side = "top",
}: {
  content?: ReactNode;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
}) {
  const enabled = content != null && content !== "";
  return (
    <TooltipProvider delayDuration={80}>
      <Tooltip open={enabled ? undefined : false}>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        {enabled ? (
          <TooltipContent
            side={side}
            className="max-w-sm px-3 py-2 text-sm leading-5 break-all"
          >
            {content}
          </TooltipContent>
        ) : null}
      </Tooltip>
    </TooltipProvider>
  );
}

/** Visible cap vs unwrapped width on the same node (no ellipsis scrollWidth, no body probe). */
function isOverflowTruncated(el: HTMLElement): boolean {
  const parent = el.parentElement;
  const cap = parent
    ? Math.min(
        el.getBoundingClientRect().width || parent.clientWidth,
        parent.clientWidth || Number.POSITIVE_INFINITY,
      )
    : el.getBoundingClientRect().width;
  if (!(cap > 0)) return false;

  const { maxWidth, width, overflow, textOverflow } = el.style;
  el.style.maxWidth = "none";
  el.style.width = "auto";
  el.style.overflow = "visible";
  el.style.textOverflow = "clip";
  const full = el.getBoundingClientRect().width;
  el.style.maxWidth = maxWidth;
  el.style.width = width;
  el.style.overflow = overflow;
  el.style.textOverflow = textOverflow;
  return full > cap + 1;
}

/** Tooltip only when this text is overflow-truncated. Hit target is the text. */
export function TruncateTip({
  text,
  className,
}: {
  text?: string | null;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);
  const shown = (text || "").trim();
  const label = shown || "—";

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !shown) {
      setTruncated(false);
      return;
    }
    const parent = el.parentElement;
    const measure = () => setTruncated(isOverflowTruncated(el));
    measure();
    if (!parent || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(parent);
    return () => ro.disconnect();
  }, [label, shown]);

  return (
    <HoverTip content={truncated && shown ? shown : undefined}>
      <span
        ref={ref}
        className={cn(className, "inline-block max-w-full truncate align-bottom")}
      >
        {label}
      </span>
    </HoverTip>
  );
}
