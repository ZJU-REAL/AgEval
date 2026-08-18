import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { splitMarkdownFrontmatter } from "@/lib/markdown-frontmatter";
import { cn } from "@/lib/utils";

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-xl font-semibold tracking-tight text-ink mt-6 mb-3 first:mt-0">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-semibold tracking-tight text-ink mt-5 mb-2 first:mt-0">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-ink mt-4 mb-2 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="text-sm text-body leading-6 mb-3 last:mb-0">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-5 mb-3 space-y-1 text-sm text-body">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 mb-3 space-y-1 text-sm text-body">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-6">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-link hover:text-link-deep underline-offset-2 hover:underline"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-hairline-strong pl-3 my-3 text-sm text-mute">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-hairline my-4" />,
  strong: ({ children }) => (
    <strong className="font-semibold text-ink">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ className, children }) => {
    const isBlock = Boolean(className);
    const text = String(children).replace(/\n$/, "");
    if (!isBlock) {
      return (
        <code className="font-mono text-[12px] bg-canvas-soft-2 text-ink px-1 py-0.5 rounded-[4px]">
          {text}
        </code>
      );
    }
    return (
      <pre
        className={cn(
          "my-3 overflow-x-auto rounded-[8px] border border-hairline",
          "bg-code-bg p-3 font-mono text-[12px] leading-5",
        )}
      >
        <code className="font-mono">{text}</code>
      </pre>
    );
  },
  pre: ({ children }) => <>{children}</>,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-[8px] border border-hairline">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-canvas-soft">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-hairline last:border-0">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left text-xs font-medium text-mute align-top whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 text-sm text-body align-top">{children}</td>
  ),
};

function FrontmatterTable({ fields }: { fields: { key: string; value: string }[] }) {
  if (!fields.length) return null;
  return (
    <dl className="mb-4 rounded-[8px] border border-hairline bg-canvas-soft overflow-hidden">
      {fields.map((field) => (
        <div
          key={field.key}
          className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 px-3 py-2 border-b border-hairline last:border-0"
        >
          <dt className="font-mono text-[11px] text-mute pt-0.5">{field.key}</dt>
          <dd className="m-0 text-sm text-body whitespace-pre-wrap break-words">
            {field.value || "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function Markdown({
  source,
  className,
}: {
  source: string;
  className?: string;
}) {
  const { fields, body } = splitMarkdownFrontmatter(source);
  return (
    <div
      className={cn(
        "rounded-[8px] border border-hairline bg-canvas p-5 max-w-none",
        className,
      )}
    >
      <FrontmatterTable fields={fields} />
      {body.trim() ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {body}
        </ReactMarkdown>
      ) : null}
    </div>
  );
}
