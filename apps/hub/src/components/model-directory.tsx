import { Link } from "react-router-dom";

import { LabGroupHead } from "@/components/lab-group-head";
import { LabMark } from "@/components/lab-mark";
import { ModalityMarks } from "@/components/modality-mark";
import { encodeDatasetId } from "@/lib/api";
import { loadModelPin, modalityBadges, modelModalities } from "@/lib/model-pin";
import { cn, formatScore } from "@/lib/utils";

export type ModelDirectoryRow = {
  overlay: string;
  canonical: string | null;
  selected?: boolean;
  isDefault?: boolean;
  suiteCount?: number;
  passRate?: number | null;
  href: string;
};

export function ModelDirectory({
  rows,
  linkCanonical = false,
}: {
  rows: ModelDirectoryRow[];
  /** When the row lands on a harness, also link the canonical id to /models. */
  linkCanonical?: boolean;
}) {
  const pin = loadModelPin();
  const labs = new Map<string, ModelDirectoryRow[]>();
  const unmatched: ModelDirectoryRow[] = [];
  for (const row of rows) {
    const lab = row.canonical ? pin.models[row.canonical]?.lab : "";
    if (!lab) {
      unmatched.push(row);
      continue;
    }
    const list = labs.get(lab) ?? [];
    list.push(row);
    labs.set(lab, list);
  }

  const groups = [...labs.entries()].sort(([a], [b]) => {
    const left = pin.labs[a]?.name || a;
    const right = pin.labs[b]?.name || b;
    return left.localeCompare(right);
  });

  return (
    <div className="space-y-5">
      {groups.map(([lab, items]) => (
        <LabGroup
          key={lab}
          lab={lab}
          name={pin.labs[lab]?.name || lab}
          rows={items}
          linkCanonical={linkCanonical}
        />
      ))}
      {unmatched.length ? (
        <LabGroup
          lab=""
          name="Unmatched"
          rows={unmatched}
          linkCanonical={false}
        />
      ) : null}
    </div>
  );
}

function LabGroup({
  lab,
  name,
  rows,
  linkCanonical,
}: {
  lab: string;
  name: string;
  rows: ModelDirectoryRow[];
  linkCanonical: boolean;
}) {
  const pin = loadModelPin();
  return (
    <section>
      <LabGroupHead lab={lab} name={name} count={rows.length} />
      <ul className="m-0 list-none divide-y divide-hairline border-y border-hairline p-0">
        {rows.map((row) => {
          const info = row.canonical ? pin.models[row.canonical] : undefined;
          const badges = info ? modalityBadges(modelModalities(info)) : [];
          return (
            <li key={`${row.overlay}\0${row.canonical || ""}`}>
              <div
                className={cn(
                  "flex items-center gap-3 px-2 py-2 text-sm",
                  "motion-safe:transition-colors motion-safe:duration-200 motion-safe:ease-smooth",
                  "hover:bg-canvas-soft",
                  row.selected && "bg-canvas-soft-2",
                )}
              >
                <Link
                  to={row.href}
                  replace={row.selected !== undefined}
                  aria-current={row.selected ? "page" : undefined}
                  className="flex min-w-0 flex-1 items-center gap-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70"
                >
                  <LabMark lab={lab || row.overlay} size={20} />
                  <span className="min-w-0 flex-1 text-left">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="font-medium text-ink">
                        {info?.name || row.overlay}
                      </span>
                      <ModalityMarks kinds={badges} />
                      {row.isDefault ? (
                        <span className="text-xs text-mute">Default</span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block truncate text-sm text-body">
                      {row.overlay}
                    </span>
                  </span>
                </Link>
                {linkCanonical && row.canonical ? (
                  <Link
                    to={`/models/${encodeDatasetId(row.canonical)}`}
                    className="shrink-0 text-sm text-link hover:text-link-deep"
                  >
                    {row.canonical}
                  </Link>
                ) : null}
                <span className="shrink-0 text-right text-sm text-mute tabular-nums">
                  {row.suiteCount != null ? (
                    <span>
                      {row.suiteCount} suite{row.suiteCount === 1 ? "" : "s"}
                    </span>
                  ) : null}
                  {row.passRate != null ? (
                    <span className="ml-3 text-ink">{formatScore(row.passRate)}</span>
                  ) : null}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
