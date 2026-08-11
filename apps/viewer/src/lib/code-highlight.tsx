/**
 * Lightweight JSON / JSONL highlighting for file preview.
 * Deterministic tokenizer — no full language server, no extra deps.
 */
import type { ReactNode } from "react";

type Kind = "key" | "string" | "number" | "bool" | "null" | "punct" | "plain";

type Token = { kind: Kind; text: string };

const KIND_CLASS: Record<Kind, string> = {
  key: "text-shell-flag",
  string: "text-shell-string",
  number: "text-shell-cmd",
  bool: "text-shell-path",
  null: "text-shell-path",
  punct: "text-shell-punct",
  plain: "text-shell-plain",
};

function tokenizeJson(src: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  let expectingKey = false;
  const stack: string[] = []; // track object vs array for key detection

  const peek = () => src[i];
  const push = (kind: Kind, text: string) => {
    tokens.push({ kind, text });
  };

  while (i < src.length) {
    const ch = peek();

    // whitespace
    if (/\s/.test(ch)) {
      let j = i + 1;
      while (j < src.length && /\s/.test(src[j])) j += 1;
      push("plain", src.slice(i, j));
      i = j;
      continue;
    }

    // punctuation
    if (ch === "{" || ch === "}" || ch === "[" || ch === "]" || ch === ":" || ch === ",") {
      if (ch === "{") {
        stack.push("obj");
        expectingKey = true;
      } else if (ch === "[") {
        stack.push("arr");
        expectingKey = false;
      } else if (ch === "}" || ch === "]") {
        stack.pop();
        expectingKey = stack[stack.length - 1] === "obj";
      } else if (ch === ":") {
        expectingKey = false;
      } else if (ch === ",") {
        expectingKey = stack[stack.length - 1] === "obj";
      }
      push("punct", ch);
      i += 1;
      continue;
    }

    // string
    if (ch === '"') {
      let j = i + 1;
      while (j < src.length) {
        if (src[j] === "\\") {
          j += 2;
          continue;
        }
        if (src[j] === '"') {
          j += 1;
          break;
        }
        j += 1;
      }
      const text = src.slice(i, j);
      // key if we are in object and expecting a key
      const isKey = expectingKey && stack[stack.length - 1] === "obj";
      push(isKey ? "key" : "string", text);
      i = j;
      continue;
    }

    // number
    if (/[0-9-]/.test(ch)) {
      let j = i + 1;
      while (j < src.length && /[0-9.eE+-]/.test(src[j])) j += 1;
      push("number", src.slice(i, j));
      i = j;
      continue;
    }

    // true / false / null
    if (src.startsWith("true", i)) {
      push("bool", "true");
      i += 4;
      continue;
    }
    if (src.startsWith("false", i)) {
      push("bool", "false");
      i += 5;
      continue;
    }
    if (src.startsWith("null", i)) {
      push("null", "null");
      i += 4;
      continue;
    }

    // fallback single char
    push("plain", ch);
    i += 1;
  }

  return tokens;
}

function tryPrettyJson(text: string): string | null {
  const t = text.trim();
  if (!t) return null;
  if (!(t.startsWith("{") || t.startsWith("["))) return null;
  try {
    return JSON.stringify(JSON.parse(t), null, 2);
  } catch {
    return null;
  }
}

function formatJsonl(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      const s = line.trim();
      if (!s) return line;
      try {
        return JSON.stringify(JSON.parse(s));
      } catch {
        return line;
      }
    })
    .join("\n");
}

export type CodeLang = "json" | "jsonl" | "text";

export function detectLang(path: string | null | undefined, content: string): CodeLang {
  const lower = (path || "").toLowerCase();
  if (lower.endsWith(".jsonl")) return "jsonl";
  if (lower.endsWith(".json")) return "json";
  // Heuristic for content without extension
  const t = content.trim();
  if (t.startsWith("{") || t.startsWith("[")) {
    try {
      JSON.parse(t);
      return "json";
    } catch {
      /* fall through */
    }
  }
  // multi-line json objects often jsonl
  const lines = t.split("\n").filter((l) => l.trim());
  if (lines.length > 1 && lines.every((l) => l.trim().startsWith("{"))) {
    return "jsonl";
  }
  return "text";
}

export function preparePreview(
  path: string | null | undefined,
  content: string,
): { lang: CodeLang; text: string } {
  const lang = detectLang(path, content);
  if (lang === "json") {
    const pretty = tryPrettyJson(content);
    return { lang, text: pretty ?? content };
  }
  if (lang === "jsonl") {
    return { lang, text: formatJsonl(content) };
  }
  return { lang: "text", text: content };
}

/** Skip tokenization for huge bodies (caller may also pre-truncate). */
const HIGHLIGHT_MAX_CHARS = 120_000;

export function CodeHighlight({
  path,
  content,
}: {
  path?: string | null;
  content: string;
}): ReactNode {
  if (content.length > HIGHLIGHT_MAX_CHARS) {
    return <span className="text-shell-plain">{content}</span>;
  }

  const { lang, text } = preparePreview(path, content);

  if (lang === "text") {
    return <span className="text-shell-plain">{text}</span>;
  }

  // jsonl: highlight each non-empty line independently so broken lines stay readable
  if (lang === "jsonl") {
    const lines = text.split("\n");
    return (
      <>
        {lines.map((line, li) => {
          if (!line.trim()) {
            return (
              <span key={li} className="text-shell-plain">
                {"\n"}
              </span>
            );
          }
          const tokens = tokenizeJson(line);
          return (
            <span key={li}>
              {tokens.map((t, ti) => (
                <span key={`${li}-${ti}`} className={KIND_CLASS[t.kind]}>
                  {t.text}
                </span>
              ))}
              {li < lines.length - 1 ? "\n" : null}
            </span>
          );
        })}
      </>
    );
  }

  const tokens = tokenizeJson(text);
  return (
    <>
      {tokens.map((t, idx) => (
        <span key={`${idx}-${t.kind}`} className={KIND_CLASS[t.kind]}>
          {t.text}
        </span>
      ))}
    </>
  );
}
