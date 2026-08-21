import type { ComponentType, KeyboardEvent, MouseEvent } from "react";
import { Bot, Puzzle } from "lucide-react";
import { Link } from "react-router-dom";

import { OfficialMark } from "@/components/official-mark";
import {
  packageDisplayTitle,
  versionLabel,
  type PackageRelease,
} from "@/lib/api";
import { cn, formatDay } from "@/lib/utils";

type CatalogKind = "plugin" | "agent";
type Glyph = ComponentType<{ className?: string; strokeWidth?: number }>;

const KIND_GLYPH: Record<CatalogKind, Glyph> = {
  plugin: Puzzle,
  agent: Bot,
};

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

function descriptionOf(kind: CatalogKind, row: PackageRelease): string | null {
  const raw =
    kind === "plugin"
      ? row.plugin_preview?.description
      : row.agent_preview?.description;
  const text = (raw || "").trim();
  return text || null;
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
  const Icon = KIND_GLYPH[kind];
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

  function onOrgClick(event: MouseEvent) {
    event.stopPropagation();
  }

  return (
    <article
      role="link"
      tabIndex={0}
      onClick={open}
      onKeyDown={onKeyDown}
      className={cn(
        "group flex h-full flex-col rounded-[12px] border border-hairline bg-canvas p-4 text-left",
        "transition-[background-color,transform,border-color] duration-200 ease-smooth",
        "hover:bg-canvas-soft motion-safe:hover:-translate-y-px",
        "active:scale-[0.99]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70",
        "cursor-pointer",
      )}
    >
      <div className="flex items-start gap-3 min-w-0">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] border border-hairline bg-canvas-soft text-mute group-hover:text-ink">
          <Icon className="h-5 w-5" strokeWidth={1.5} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="inline-flex min-w-0 items-center gap-1.5 font-medium text-ink">
              <span className="truncate">{title}</span>
              {row.official ? <OfficialMark /> : null}
            </p>
            <span className="shrink-0 font-mono text-[11px] tabular-nums text-mute">
              {versionLabel(row)}
            </span>
          </div>
          <p className="mt-0.5 font-mono text-[11px] text-mute truncate">
            {row.dataset_id}
          </p>
        </div>
      </div>

      {description ? (
        <p className="mt-3 line-clamp-2 text-sm text-body">{description}</p>
      ) : (
        <p className="mt-3 text-sm text-mute">
          {kind === "plugin" ? "ageval.plugin/1 package" : "ageval.agent/1 package"}
        </p>
      )}

      {chips.length ? (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {chips.map((chip) => (
            <li
              key={chip}
              className="rounded-[6px] bg-canvas-soft px-1.5 py-0.5 font-mono text-[11px] text-body"
            >
              {chip}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-auto flex items-center justify-between gap-2 pt-4 text-[11px] text-mute">
        {row.org_id ? (
          <Link
            to={`/organizations/${encodeURIComponent(row.org_id)}`}
            onClick={onOrgClick}
            className="inline-flex min-w-0 items-center gap-1 font-mono hover:text-ink"
          >
            <span className="truncate">@{row.org_id}</span>
            {row.official ? <OfficialMark kind="org" /> : null}
          </Link>
        ) : (
          <span>—</span>
        )}
        <span className="flex shrink-0 items-center gap-2 tabular-nums">
          <span>{row.visibility}</span>
          {updated ? <span>{updated}</span> : null}
        </span>
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
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {rows.map((row) => (
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
