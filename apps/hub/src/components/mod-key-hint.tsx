import { Command } from "lucide-react";

import { useModKey } from "@/hooks/use-mod-key";

const kbdIcon =
  "inline-flex size-5 items-center justify-center rounded-[8px] border border-hairline";
const kbdText =
  "inline-flex h-5 min-w-5 items-center justify-center rounded-[8px] border border-hairline px-1 text-xs leading-none";

/** One modifier keycap for the current OS, then the letter. */
export function ModKeyHint({ keycap }: { keycap: string }) {
  const mod = useModKey();
  return (
    <span
      className="inline-flex shrink-0 items-center gap-0.5 text-mute"
      aria-hidden
    >
      {mod === "meta" ? (
        <kbd className={kbdIcon}>
          <Command className="size-3" strokeWidth={2} />
        </kbd>
      ) : (
        <kbd className={kbdText}>Ctrl</kbd>
      )}
      <kbd className={kbdText}>{keycap}</kbd>
    </span>
  );
}
