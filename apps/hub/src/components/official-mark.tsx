import { BadgeCheck } from "lucide-react";

import { HoverTip } from "@/components/hover-tip";

const TIP = "Verified official plugin";

export function OfficialMark({ className = "" }: { className?: string }) {
  return (
    <HoverTip content={TIP}>
      <span
        className={`inline-flex shrink-0 text-link ${className}`.trim()}
        aria-label={TIP}
        onClick={(event) => event.stopPropagation()}
      >
        <BadgeCheck className="size-4" strokeWidth={2} aria-hidden />
      </span>
    </HoverTip>
  );
}
