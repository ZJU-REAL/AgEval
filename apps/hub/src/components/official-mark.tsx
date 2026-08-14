import { BadgeCheck } from "lucide-react";

import { HoverTip } from "@/components/hover-tip";

const PLUGIN_TIP = "Verified official plugin";
const ORG_TIP = "Verified official organization";

export function OfficialMark({
  className = "",
  kind = "plugin",
}: {
  className?: string;
  kind?: "plugin" | "org";
}) {
  const tip = kind === "org" ? ORG_TIP : PLUGIN_TIP;
  return (
    <HoverTip content={tip}>
      <span
        className={`inline-flex shrink-0 text-link ${className}`.trim()}
        aria-label={tip}
        onClick={(event) => event.stopPropagation()}
      >
        <BadgeCheck className="size-4" strokeWidth={2} aria-hidden />
      </span>
    </HoverTip>
  );
}
