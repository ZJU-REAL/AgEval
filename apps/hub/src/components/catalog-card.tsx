import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { BrandMark } from "@/components/brand-mark";
import { OfficialMark } from "@/components/official-mark";
import { DownloadCount } from "@/components/download-count";
import { markFromPackage } from "@/lib/brand-marks";
import {
  getPackageByDigest,
  packageDisplayTitle,
  type PackageRelease,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { cn, formatDay } from "@/lib/utils";

type CatalogKind = "plugin" | "agent";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function pluginChips(row: PackageRelease): string[] {
  const preview = row.plugin_preview;
  if (!preview) return [];
  const exclusive = preview.slots?.exclusive ?? [];
  const chain = preview.slots?.chain ?? [];
  const declared = (preview.declared ?? []).map((slot) => slot.id);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of [...exclusive, ...chain, ...declared]) {
    const key = id.trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(key);
  }
  return out.slice(0, 4);
}

function agentChips(row: PackageRelease): string[] {
  const binding = row.agent_preview?.binding;
  if (!binding || typeof binding !== "object") return [];
  const executor = asString(binding.executor);
  const model = asString(binding.model);
  const chips: string[] = [];
  if (executor) chips.push(executor);
  if (model) chips.push(model);
  return chips;
}

function hasPreview(kind: CatalogKind, row: PackageRelease): boolean {
  return kind === "plugin" ? Boolean(row.plugin_preview) : Boolean(row.agent_preview);
}

function descriptionOf(kind: CatalogKind, row: PackageRelease): string | null {
  const raw =
    kind === "plugin"
      ? row.plugin_preview?.description
      : row.agent_preview?.description;
  const text = (raw || "").replace(/\s+/g, " ").trim();
  return text || null;
}

function rowKey(row: PackageRelease): string {
  return `${row.dataset_id}@${row.package_digest}`;
}

export function CatalogCard({
  kind,
  row,
  onOpen,
}: {
  kind: CatalogKind;
  row: PackageRelease;
  onOpen: (id: string) => void;
}) {
  const title = packageDisplayTitle(row.dataset_id, row.display_name);
  const chips = kind === "plugin" ? pluginChips(row) : agentChips(row);
  const description = descriptionOf(kind, row);
  const updated = row.created_at != null ? formatDay(row.created_at) : null;

  function open() {
    onOpen(row.dataset_id);
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      open();
    }
  }

  return (
    <article
      role="link"
      tabIndex={0}
      onClick={open}
      onKeyDown={onKeyDown}
      className={cn(
        "flex h-full flex-col rounded-[12px] border border-hairline bg-canvas p-4 text-left",
        "transition-colors duration-200 ease-smooth",
        "hover:bg-canvas-soft",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70",
        "cursor-pointer",
      )}
    >
      <div className="min-w-0">
        <div className="flex items-end justify-between gap-2">
          <p className="inline-flex min-w-0 items-end gap-2 font-medium leading-none text-ink">
            <BrandMark mark={markFromPackage(row)} size={24} />
            <span className="truncate leading-none">{title}</span>
            {row.official ? <OfficialMark /> : null}
          </p>
          {updated ? (
            <span className="shrink-0 font-mono text-[11px] leading-none tabular-nums text-mute">
              {updated}
            </span>
          ) : null}
        </div>
      </div>

      <p
        className={cn(
          "mt-3 h-10 line-clamp-2 text-sm leading-5",
          description ? "text-body" : "text-mute",
        )}
        title={description ?? undefined}
      >
        {description ??
          (kind === "plugin"
            ? "ageval.plugin/1 package"
            : "ageval.agent/1 package")}
      </p>

      <div className="mt-auto flex items-end justify-between gap-2 pt-3">
        {chips.length ? (
          <ul className="flex min-w-0 flex-wrap gap-1.5">
            {chips.map((chip) => (
              <li
                key={chip}
                className="rounded-[6px] bg-canvas-soft px-1.5 py-0.5 font-mono text-[11px] text-body"
              >
                {chip}
              </li>
            ))}
          </ul>
        ) : (
          <span />
        )}
        <DownloadCount count={row.download_count} compact className="shrink-0" />
      </div>
    </article>
  );
}

export function CatalogCardGrid({
  kind,
  rows,
  onOpen,
}: {
  kind: CatalogKind;
  rows: PackageRelease[];
  onOpen: (id: string) => void;
}) {
  const [previews, setPreviews] = useState<Record<string, PackageRelease>>({});
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const missingKey = rows
    .filter((row) => !hasPreview(kind, row))
    .map(rowKey)
    .join("\n");

  useEffect(() => {
    const pending = rowsRef.current.filter((row) => !hasPreview(kind, row));
    if (!pending.length) return;
    let cancelled = false;
    const token = getToken();
    void Promise.all(
      pending.map(async (row) => {
        try {
          const meta = await getPackageByDigest(
            row.dataset_id,
            row.package_digest,
            token,
          );
          return [rowKey(row), meta] as const;
        } catch {
          return null;
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      const next: Record<string, PackageRelease> = {};
      for (const entry of entries) {
        if (entry) next[entry[0]] = entry[1];
      }
      if (Object.keys(next).length) {
        setPreviews((prev) => ({ ...prev, ...next }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [kind, missingKey]);

  const resolved = useMemo(
    () =>
      rows.map((row) => {
        if (hasPreview(kind, row)) return row;
        const extra = previews[rowKey(row)];
        return extra ?? row;
      }),
    [kind, rows, previews],
  );

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {resolved.map((row) => (
        <CatalogCard
          key={`${row.dataset_id}@${row.version}`}
          kind={kind}
          row={row}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}

export function CatalogCardSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
      aria-hidden
    >
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="h-[168px] rounded-[12px] border border-hairline bg-canvas-soft motion-safe:animate-pulse"
        />
      ))}
    </div>
  );
}
