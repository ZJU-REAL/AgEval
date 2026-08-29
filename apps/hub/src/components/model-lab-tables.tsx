import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { LabGroupHead } from "@/components/lab-group-head";
import { ModalityMarks } from "@/components/modality-mark";
import {
  SortableHead,
  compareValues,
  nextSort,
  type SortDir,
} from "@/components/sortable-head";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { encodeDatasetId } from "@/lib/api";
import {
  compactTokens,
  directoryPrice,
  fmtPrice,
  loadModelPin,
  modalityBadges,
  modelModalities,
} from "@/lib/model-pin";

export type ModelLabRow = {
  overlay: string;
  canonical: string | null;
};

const CELL_MUTE = "whitespace-nowrap text-sm text-mute tabular-nums";
const CELL_INK = "whitespace-nowrap text-sm text-ink tabular-nums";

/** Shared across every lab table so columns line up. */
const COLS = (
  <colgroup>
    <col className="w-[44%]" />
    <col className="w-[14%]" />
    <col className="w-[12%]" />
    <col className="w-[12%]" />
    <col className="w-[18%]" />
  </colgroup>
);

const STICKY_TH = "sticky z-10 bg-canvas-soft top-[var(--models-stick-top,0px)]";

export function ModelLabTables({ rows }: { rows: ModelLabRow[] }) {
  const pin = loadModelPin();
  const [sortKey, setSortKey] = useState<string | null>("released");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function onSort(key: string) {
    const next = nextSort(sortKey, sortDir, key);
    setSortKey(next.dir ? next.key : null);
    setSortDir(next.dir);
  }

  function head(key: string, label: string) {
    return (
      <SortableHead
        label={label}
        active={sortKey === key}
        dir={sortKey === key ? sortDir : null}
        onClick={() => onSort(key)}
      />
    );
  }

  const labs = useMemo(() => {
    const map = new Map<string, ModelLabRow[]>();
    for (const row of rows) {
      const lab = row.canonical ? (pin.models[row.canonical]?.lab ?? "") : "";
      const list = map.get(lab) ?? [];
      list.push(row);
      map.set(lab, list);
    }
    return [...map.entries()].sort(([a], [b]) =>
      (pin.labs[a]?.name || a).localeCompare(pin.labs[b]?.name || b),
    );
  }, [rows, pin]);

  const infoOf = (row: ModelLabRow) =>
    row.canonical ? pin.models[row.canonical] : undefined;

  function fallback(a: ModelLabRow, b: ModelLabRow): number {
    const ai = infoOf(a);
    const bi = infoOf(b);
    const cmp = compareValues(ai?.release_date || null, bi?.release_date || null, "desc");
    if (cmp !== 0) return cmp;
    return (ai?.name || a.overlay).localeCompare(bi?.name || b.overlay);
  }

  function sortValue(row: ModelLabRow, key: string): string | number | null {
    const info = infoOf(row);
    if (!info) return null;
    if (key === "model") return info.name || row.overlay;
    if (key === "released") return info.release_date || null;
    if (key === "context") return info.context;
    if (key === "output") return info.output;
    if (key === "price") {
      const price = row.canonical ? directoryPrice(row.canonical, row.canonical, pin) : null;
      return price ? price.input : null;
    }
    return null;
  }

  function sortItems(items: ModelLabRow[]): ModelLabRow[] {
    const sorted = [...items];
    if (sortKey && sortDir) {
      sorted.sort((a, b) => {
        const cmp = compareValues(sortValue(a, sortKey), sortValue(b, sortKey), sortDir);
        return cmp !== 0 ? cmp : fallback(a, b);
      });
    } else {
      sorted.sort(fallback);
    }
    return sorted;
  }

  const labIds = useMemo(
    () => labs.map(([lab]) => lab || "unmatched"),
    [labs],
  );
  const headEls = useRef(new Map<string, HTMLElement>());
  const [pinned, setPinned] = useState<string | null>(null);
  const pinSlot =
    typeof document !== "undefined" ? document.getElementById("models-lab-pin") : null;

  useEffect(() => {
    const chrome = document.getElementById("models-chrome");
    const main = document.getElementById("main");
    if (!chrome || !main) return;
    const apply = () => {
      const line = chrome.getBoundingClientRect().bottom;
      let next: string | null = null;
      for (const id of labIds) {
        const el = headEls.current.get(id);
        if (el && el.getBoundingClientRect().top <= line + 0.5) next = id;
      }
      setPinned(next);
    };
    main.addEventListener("scroll", apply, { passive: true });
    window.addEventListener("resize", apply);
    apply();
    return () => {
      main.removeEventListener("scroll", apply);
      window.removeEventListener("resize", apply);
    };
  }, [labIds]);

  const pinnedLab = labs.find(([lab]) => (lab || "unmatched") === pinned);

  return (
    <div>
      {pinned && pinnedLab && pinSlot
        ? createPortal(
            <PinnedLabSwap
              id={pinned}
              lab={pinnedLab[0]}
              name={pin.labs[pinnedLab[0]]?.name || pinnedLab[0] || "Unmatched"}
              count={sortItems(pinnedLab[1]).length}
              order={labIds}
            />,
            pinSlot,
          )
        : null}
      {labs.map(([lab, items], i) => {
        const sorted = sortItems(items);
        const id = lab || "unmatched";
        return (
          <LabSection
            key={id}
            first={i === 0}
            pinned={pinned === id}
            onHead={(el) => {
              if (el) headEls.current.set(id, el);
              else headEls.current.delete(id);
            }}
            head={
              <LabGroupHead
                lab={lab}
                name={pin.labs[lab]?.name || lab || "Unmatched"}
                count={sorted.length}
              />
            }
            columns={
              <>
                <TableHead className={STICKY_TH}>{head("model", "Model")}</TableHead>
                <TableHead className={STICKY_TH}>{head("released", "Released")}</TableHead>
                <TableHead className={STICKY_TH}>{head("context", "Context")}</TableHead>
                <TableHead className={STICKY_TH}>{head("output", "Output")}</TableHead>
                <TableHead className={STICKY_TH}>{head("price", "Price / MTok")}</TableHead>
              </>
            }
          >
            <TableBody>
                {sorted.map((row) => {
                  const info = infoOf(row);
                  const badges = info ? modalityBadges(modelModalities(info)) : [];
                  const price = row.canonical
                    ? directoryPrice(row.canonical, row.canonical, pin)
                    : null;
                  return (
                    <TableRow key={row.overlay}>
                      <TableCell className="whitespace-normal overflow-visible">
                        <span className="flex min-w-0 flex-col items-start gap-0.5">
                          <span className="flex min-w-0 flex-wrap items-center gap-2">
                            {row.canonical ? (
                              <Link
                                to={`/models/${encodeDatasetId(row.canonical)}`}
                                className="shrink-0 font-medium text-ink hover:text-link-deep hover:underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-link/70"
                              >
                                {info?.name || row.overlay}
                              </Link>
                            ) : (
                              <span className="shrink-0 font-medium text-ink">
                                {row.overlay}
                              </span>
                            )}
                            {badges.length ? <ModalityMarks kinds={badges} /> : null}
                          </span>
                          <span className="max-w-full truncate text-[13px] text-mute">
                            {row.canonical || row.overlay}
                          </span>
                        </span>
                      </TableCell>
                      <TableCell className={CELL_MUTE}>
                        {info?.release_date || "—"}
                      </TableCell>
                      <TableCell
                        className={CELL_INK}
                        title={
                          info?.context != null
                            ? `${info.context.toLocaleString()} tok`
                            : undefined
                        }
                      >
                        {info?.context != null ? compactTokens(info.context) : "—"}
                      </TableCell>
                      <TableCell
                        className={CELL_MUTE}
                        title={
                          info?.output != null
                            ? `${info.output.toLocaleString()} tok`
                            : undefined
                        }
                      >
                        {info?.output != null ? compactTokens(info.output) : "—"}
                      </TableCell>
                      <TableCell
                        className={CELL_MUTE}
                        title={price ? `pin snapshot · ${price.provider}` : undefined}
                      >
                        {price
                          ? `$${fmtPrice(price.input)} / $${fmtPrice(price.output)}`
                          : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
          </LabSection>
        );
      })}
    </div>
  );
}

function PinnedLabSwap({
  id,
  lab,
  name,
  count,
  order,
}: {
  id: string;
  lab: string;
  name: string;
  count: number;
  order: string[];
}) {
  const liveRef = useRef({ id, lab, name, count });
  const [live, setLive] = useState({ id, lab, name, count });
  const [exit, setExit] = useState<{
    id: string;
    lab: string;
    name: string;
    count: number;
  } | null>(null);
  const [dir, setDir] = useState<1 | -1>(1);

  useEffect(() => {
    const prev = liveRef.current;
    if (prev.id === id) {
      liveRef.current = { id, lab, name, count };
      setLive({ id, lab, name, count });
      return;
    }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const from = order.indexOf(prev.id);
    const to = order.indexOf(id);
    setDir(to >= from ? 1 : -1);
    if (!reduced) setExit(prev);
    liveRef.current = { id, lab, name, count };
    setLive({ id, lab, name, count });
    if (reduced) return;
    const t = window.setTimeout(() => setExit(null), 200);
    return () => window.clearTimeout(t);
  }, [id, lab, name, count, order]);

  return (
    <div className="relative overflow-hidden">
      {exit ? (
        <div
          aria-hidden
          data-ageval-lab-out=""
          className="pointer-events-none absolute inset-x-0 top-0"
          style={{ ["--lab-dy" as string]: dir > 0 ? "-8px" : "8px" }}
        >
          <LabGroupHead lab={exit.lab} name={exit.name} count={exit.count} />
        </div>
      ) : null}
      <div
        key={live.id}
        data-ageval-lab-in=""
        style={{ ["--lab-dy" as string]: dir > 0 ? "8px" : "-8px" }}
      >
        <LabGroupHead lab={live.lab} name={live.name} count={live.count} />
      </div>
    </div>
  );
}

function LabSection({
  first,
  head,
  pinned,
  onHead,
  columns,
  children,
}: {
  first: boolean;
  head: ReactNode;
  pinned: boolean;
  onHead: (el: HTMLElement | null) => void;
  columns: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className={first ? undefined : "mt-8"}>
      <div ref={onHead} className={pinned ? "invisible pb-2" : "pb-2"}>
        {head}
      </div>
      <div className="blob-panel">
        <Table
          wrapClassName="overflow-visible"
          className="border-separate border-spacing-0"
        >
          {COLS}
          <TableHeader>
            <TableRow className="hover:bg-transparent">{columns}</TableRow>
          </TableHeader>
          {children}
        </Table>
      </div>
    </section>
  );
}
