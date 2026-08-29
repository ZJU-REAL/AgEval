import { ModelItem } from "@/components/model-item";

export type ModelDirectoryRow = {
  overlay: string;
  canonical: string | null;
  selected?: boolean;
  isDefault?: boolean;
  href: string;
};

/** Flat ModelItem list for a harness. No lab/provider grouping. */
export function ModelDirectory({ rows }: { rows: ModelDirectoryRow[] }) {
  return (
    <div
      className="grid max-h-[calc(3*var(--model-row)+2*0.5rem)] grid-cols-1 gap-2 overflow-y-auto overscroll-contain lg:grid-cols-2 [--model-row:4rem]"
    >
      {rows.map((row) => (
        <ModelItem
          key={`${row.overlay}\0${row.canonical || ""}`}
          canonical={row.canonical}
          overlay={row.overlay}
          selected={row.selected}
          href={row.href}
          replace={row.selected !== undefined}
          meta="compact"
          className="h-[var(--model-row)] min-w-0 overflow-hidden border border-hairline"
          extra={
            row.isDefault ? (
              <span className="text-xs text-mute">Default</span>
            ) : null
          }
        />
      ))}
    </div>
  );
}
