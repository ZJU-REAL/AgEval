"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

const INSTALL = "uv tool install ageval-cli";
const SKILLS = "npx skills add ZJU-REAL/ageval";
const COPY_TEXT = `${INSTALL}\n${SKILLS}`;

type StartCodeProps = {
  label: string;
  copyLabel: string;
  copiedLabel: string;
};

export function StartCode({ label, copyLabel, copiedLabel }: StartCodeProps) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    await navigator.clipboard.writeText(COPY_TEXT);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="start-code">
      <div className="start-head">
        <p className="start-label">{label}</p>
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
      <pre className="start-snippet" tabIndex={0}>
        <span className="prompt">$ </span>
        {INSTALL}
        {"\n"}
        <span className="prompt">$ </span>
        {SKILLS}
      </pre>
    </div>
  );
}
