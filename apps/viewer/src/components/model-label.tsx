import { HoverTip, TruncateTip } from "@/components/hover-tip";
import { cn, formatModelLabel } from "@/lib/utils";

export function ModelLabel({
  value,
  effort,
  className,
  empty = "-",
}: {
  value?: string | null;
  effort?: string | null;
  className?: string;
  empty?: string;
}) {
  const { text, title } = formatModelLabel(value, effort);
  const shown = text === "-" ? empty : text;
  if (!value?.trim() || shown === empty) {
    return <span className={className}>{shown}</span>;
  }
  if (title && title !== shown) {
    return (
      <HoverTip content={title}>
        <span
          className={cn(className, "inline-block w-max max-w-full cursor-help")}
        >
          {shown}
        </span>
      </HoverTip>
    );
  }
  return <TruncateTip text={shown} className={className} />;
}
