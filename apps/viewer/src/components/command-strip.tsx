import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ShellCode } from "@/lib/shell-highlight";
import { cn } from "@/lib/utils";

export function CommandStrip({
  command,
  className,
}: {
  command: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  }

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-[8px] border border-hairline bg-code-bg px-3 py-2.5",
        className,
      )}
    >
      <pre
        className="flex-1 m-0 overflow-x-auto font-mono text-[13px] leading-5 whitespace-nowrap"
        aria-label="Shell command"
      >
        <code className="font-mono">
          <ShellCode command={command} />
        </code>
      </pre>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onCopy}
        aria-label="Copy command"
        className="shrink-0"
      >
        {copied ? (
          <Check className="h-4 w-4 text-ink" />
        ) : (
          <Copy className="h-4 w-4 text-mute" />
        )}
      </Button>
    </div>
  );
}
