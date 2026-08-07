import { useEffect, useState } from "react";

import { Markdown } from "@/components/markdown";
import { codeToHtml, isMarkdownPath } from "@/lib/shiki-preview";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/**
 * Files-tab right pane: Markdown (GFM) for .md; Shiki multi-color for code.
 */
export function FilePreview({
  path,
  content,
  note,
}: {
  path: string | null;
  content: string;
  note?: string | null;
}) {
  const { resolved } = useTheme();
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const markdown = isMarkdownPath(path);

  useEffect(() => {
    if (markdown) {
      setHtml(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setHtml(null);
    setError(null);
    void codeToHtml(content, path, resolved)
      .then((out) => {
        if (!cancelled) setHtml(out);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          // plain fallback
          setHtml(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [content, path, resolved, markdown]);

  if (note) {
    // note still shown above content by parent optionally
  }

  if (markdown) {
    return (
      <div className="p-4 overflow-auto h-full">
        {note ? <p className="text-xs text-mute mb-2">{note}</p> : null}
        <Markdown source={content} className="border-0 rounded-none p-0" />
      </div>
    );
  }

  if (error) {
    return (
      <pre
        className={cn(
          "m-0 p-3 min-h-full overflow-auto",
          "whitespace-pre-wrap break-words font-mono text-[12px] leading-5",
          "bg-code-bg text-shell-plain",
        )}
      >
        {content}
      </pre>
    );
  }

  if (!html) {
    return <p className="text-sm text-mute p-3">Highlighting…</p>;
  }

  return (
    <div className="h-full overflow-auto bg-code-bg">
      {note ? <p className="text-xs text-mute px-3 pt-2">{note}</p> : null}
      <div
        className="shiki-preview text-[12px] leading-5 [&_pre]:m-0 [&_pre]:p-3 [&_pre]:overflow-x-auto [&_pre]:!bg-transparent [&_code]:font-mono [&_code]:text-[12px] [&_code]:leading-5"
        // Shiki trusts its own HTML; content is package file body (operator-controlled).
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
