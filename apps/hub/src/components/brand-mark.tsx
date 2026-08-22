import { BrandMarkSvg, type ResolvedMark } from "@/lib/brand-marks";
import { cn } from "@/lib/utils";

export function BrandMark({
  mark,
  size = 16,
  className,
  title,
}: {
  mark: ResolvedMark;
  size?: number;
  className?: string;
  title?: string;
}) {
  if (mark.key) {
    return (
      <span
        className={cn("inline-flex shrink-0 text-ink", className)}
        title={title}
        style={{ width: size, height: size }}
      >
        <BrandMarkSvg id={mark.key} size={size} />
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-[6px] bg-canvas-soft font-mono font-medium text-mute",
        className,
      )}
      title={title}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.48) }}
      aria-hidden
    >
      {mark.letter}
    </span>
  );
}
