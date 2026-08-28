import { Check, Copy } from "lucide-react";
import {
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

export function HoverTip({
  content,
  children,
}: {
  content?: ReactNode;
  children: ReactElement;
}) {
  const enabled = content != null && content !== "";
  return (
    <TooltipProvider delayDuration={80}>
      <Tooltip open={enabled ? undefined : false}>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        {enabled ? (
          <TooltipContent
            side="top"
            className="max-w-sm px-3 py-2 text-sm leading-5 break-all"
          >
            {content}
          </TooltipContent>
        ) : null}
      </Tooltip>
    </TooltipProvider>
  );
}

/** Visible cap vs unwrapped content width. Table cells clip the paint; flex used width can still be full. */
function isOverflowTruncated(el: HTMLElement): boolean {
  const cell = el.closest("td, th");
  const painted = el.getBoundingClientRect().width;
  const cap = Math.min(
    painted || Number.POSITIVE_INFINITY,
    cell instanceof HTMLElement && cell.clientWidth > 0
      ? cell.clientWidth
      : Number.POSITIVE_INFINITY,
    el.parentElement && el.parentElement.clientWidth > 0
      ? el.parentElement.clientWidth
      : Number.POSITIVE_INFINITY,
  );
  if (!(cap > 0) || !Number.isFinite(cap)) return false;

  const prev = {
    maxWidth: el.style.maxWidth,
    width: el.style.width,
    overflow: el.style.overflow,
    textOverflow: el.style.textOverflow,
    flex: el.style.flex,
    whiteSpace: el.style.whiteSpace,
  };
  el.style.maxWidth = "none";
  el.style.width = "max-content";
  el.style.flex = "0 0 auto";
  el.style.overflow = "visible";
  el.style.textOverflow = "clip";
  el.style.whiteSpace = "nowrap";
  const full = Math.max(el.scrollWidth, el.getBoundingClientRect().width);
  el.style.maxWidth = prev.maxWidth;
  el.style.width = prev.width;
  el.style.overflow = prev.overflow;
  el.style.textOverflow = prev.textOverflow;
  el.style.flex = prev.flex;
  el.style.whiteSpace = prev.whiteSpace;
  return full > cap + 1;
}

/** Tooltip only when this text is overflow-truncated. Hit target is the text. */
export function TruncateTip({
  text,
  className,
  copyable = false,
  copyValue,
}: {
  text?: string | null;
  className?: string;
  copyable?: boolean;
  copyValue?: string | null;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [truncated, setTruncated] = useState(false);
  const [copied, setCopied] = useState(false);
  const shown = (text || "").trim();
  const label = shown || "—";
  const payload = (copyValue ?? shown).trim();
  const canCopy = copyable && Boolean(payload);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || !shown) {
      setTruncated(false);
      return;
    }
    const parent = el.parentElement;
    const measure = () => setTruncated(isOverflowTruncated(el));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    if (parent) ro.observe(parent);
    ro.observe(el);
    return () => ro.disconnect();
  }, [label, shown]);

  function copy(event: MouseEvent<HTMLButtonElement>) {
    if (!canCopy) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.blur();
    void navigator.clipboard.writeText(payload).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
        toast("Copied");
      },
      () => toast("Copy failed", { tone: "error" }),
    );
  }

  const textSpan = (
    <span
      ref={ref}
      className={cn(className, "min-w-0 flex-1 truncate align-bottom")}
    >
      {label}
    </span>
  );

  return (
    <span className="group/copy inline-flex min-w-0 max-w-full items-center">
      <HoverTip content={truncated && shown ? shown : undefined}>{textSpan}</HoverTip>
      {canCopy ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={copied ? "Copied" : `Copy ${payload}`}
          onClick={copy}
          className="ml-1.5 h-6 w-6 shrink-0 opacity-0 pointer-events-none hover:bg-liquid-hover motion-safe:transition-opacity motion-safe:duration-200 motion-safe:ease-smooth group-hover/copy:pointer-events-auto group-hover/copy:opacity-100 focus-visible:pointer-events-auto focus-visible:opacity-100"
        >
          <span className="relative h-3.5 w-3.5">
            <Copy
              className={cn(
                "absolute inset-0 h-3.5 w-3.5 text-mute motion-safe:transition-[opacity,transform] motion-safe:duration-200 motion-safe:ease-smooth",
                copied ? "scale-50 opacity-0" : "scale-100 opacity-100",
              )}
            />
            <Check
              className={cn(
                "absolute inset-0 h-3.5 w-3.5 text-ink motion-safe:transition-[opacity,transform] motion-safe:duration-200 motion-safe:ease-spring",
                copied ? "scale-100 opacity-100" : "scale-50 opacity-0",
              )}
            />
          </span>
        </Button>
      ) : null}
    </span>
  );
}
