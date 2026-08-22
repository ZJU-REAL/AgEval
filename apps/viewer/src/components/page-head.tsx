import type { ReactNode } from "react";

import { useDocumentTitle } from "@/lib/document-title";

type PageHeadProps = {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
};

/** Page header: title + optional sub over a hairline rule. */
export function PageHead({ title, sub, actions }: PageHeadProps) {
  const text = typeof title === "string" ? title : null;
  useDocumentTitle(text);

  return (
    <header className="mb-5 border-b border-hairline pb-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            {title}
          </h1>
          {sub ? <p className="mt-1 text-sm text-body">{sub}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
