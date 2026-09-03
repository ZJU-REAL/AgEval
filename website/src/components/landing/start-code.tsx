"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

const QUICK = ["uv tool install ageval-cli", "npx skills add ZJU-REAL/ageval"];
const SOURCE = [
  "git clone https://github.com/ZJU-REAL/ageval.git && cd ageval",
  "uv sync --frozen --all-packages",
];

type StartCodeProps = {
  tabs: readonly string[];
  copyLabel: string;
  copiedLabel: string;
};

export function StartCode({ tabs, copyLabel, copiedLabel }: StartCodeProps) {
  const [tab, setTab] = useState(0);
  const [copied, setCopied] = useState(false);
  const lines = tab === 0 ? QUICK : SOURCE;

  async function onCopy() {
    await navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  function onTabKey(event: React.KeyboardEvent) {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (tab + delta + tabs.length) % tabs.length;
    setTab(next);
    document.getElementById(`start-tab-${next}`)?.focus();
  }

  return (
    <div className="start-code">
      <div className="start-head">
        <div className="start-tabs" role="tablist" onKeyDown={onTabKey}>
          {tabs.map((label, index) => (
            <button
              key={label}
              type="button"
              role="tab"
              id={`start-tab-${index}`}
              aria-selected={tab === index}
              aria-controls="start-panel"
              tabIndex={tab === index ? 0 : -1}
              className="start-tab"
              onClick={() => setTab(index)}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="start-copy"
          onClick={onCopy}
          aria-live="polite"
        >
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? copiedLabel : copyLabel}
        </button>
      </div>
      <pre className="start-snippet" id="start-panel" role="tabpanel" tabIndex={0}>
        {lines.map((line, index) => (
          <span key={line}>
            <span className="prompt">$ </span>
            {line}
            {index < lines.length - 1 ? "\n" : null}
          </span>
        ))}
      </pre>
    </div>
  );
}
