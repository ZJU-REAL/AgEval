import { Bot } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  listRuntimes,
  RegistryHttpError,
  type RuntimeCard,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

function listDisplayName(card: RuntimeCard, all: RuntimeCard[]): string {
  const clash = all.some(
    (other) =>
      other.display_name === card.display_name &&
      other.runtime_id !== card.runtime_id,
  );
  if (!clash) return card.display_name;
  return `${card.display_name} · ${card.runtime_id.slice(3, 9)}`;
}

export function RuntimesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<RuntimeCard[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const token = getToken();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listRuntimes(token)
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof RegistryHttpError) {
          setError(`${err.code}: ${err.message}`);
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  function openRuntime(id: string) {
    navigate(`/runtimes/${encodeURIComponent(id)}`);
  }

  return (
    <>
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Runtimes
        </h1>
        <p className="text-sm text-body mt-1">
          Agents on official public Leaderboards. Derived view — not a stored
          Runtime object and not suite PASS.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-mute">Loading…</p>
      ) : error ? (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft p-4 text-sm text-body">
          <p className="text-error font-medium">Could not load runtimes</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm text-body">
          <div className="flex justify-center mb-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
              <Bot className="h-8 w-8" strokeWidth={1.5} aria-hidden />
            </div>
          </div>
          <p className="font-medium text-ink">No runtimes yet</p>
          <p className="mt-1 text-mute max-w-md mx-auto">
            Official public boards have no extractable bindings yet.
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-[8px] border border-hairline overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>Display name</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead className="text-right tabular-nums">
                    Datasets
                  </TableHead>
                  <TableHead className="text-right tabular-nums">
                    Results
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((row) => (
                  <TableRow
                    key={row.runtime_id}
                    className="cursor-pointer"
                    onClick={() => openRuntime(row.runtime_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openRuntime(row.runtime_id);
                      }
                    }}
                    tabIndex={0}
                    role="link"
                  >
                    <TableCell className="font-medium text-sm">
                      {listDisplayName(row, items)}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-body">
                      {row.entry || "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-body">
                      {row.n_datasets}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-body">
                      {row.n_appearances}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <p className="text-xs text-mute mt-3 tabular-nums">
            {items.length} runtime{items.length === 1 ? "" : "s"}
          </p>
        </>
      )}
    </>
  );
}
