import type { MouseEvent } from "react";
import { Link } from "react-router-dom";

import { HoverTip, TruncateTip } from "@/components/hover-tip";
import { cn, formatModelLabel } from "@/lib/utils";

export function ModelLabel({
  value,
  effort,
  className,
  empty = "-",
  to,
  onClick,
}: {
  value?: string | null;
  effort?: string | null;
  className?: string;
  empty?: string;
  /** When set, only the model name is a link; ``[effort]`` stays outside. */
  to?: string;
  onClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
}) {
  const { text, title } = formatModelLabel(value);
  const extra = (effort || "").trim();
  const shown = text === "-" ? empty : text;
  if (!value?.trim() || shown === empty) {
    return <span className={className}>{shown}</span>;
  }

  const model =
    title && title !== shown ? (
      <HoverTip content={title}>
        <span
          className={cn(
            "inline-block w-max min-w-0 max-w-full truncate",
            !to && "cursor-help",
          )}
        >
          {shown}
        </span>
      </HoverTip>
    ) : (
      <TruncateTip text={shown} />
    );

  return (
    <span className={cn("inline-flex min-w-0 max-w-full items-baseline", className)}>
      {to ? (
        <Link
          to={to}
          onClick={onClick}
          className="inline-flex min-w-0 text-link hover:text-link-deep hover:underline underline-offset-2"
        >
          {model}
        </Link>
      ) : (
        model
      )}
      {extra ? <span className="shrink-0 text-mute">[{extra}]</span> : null}
    </span>
  );
}
