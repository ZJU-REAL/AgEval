import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Boxes } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { LabMark } from "@/components/lab-mark";
import { ModalityMarks } from "@/components/modality-mark";
import { CatalogHead } from "@/components/page-head";
import { ScoreRing } from "@/components/score-ring";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { agentPackageHref } from "@/lib/agent-models";
import { decodeDatasetId, encodeDatasetId } from "@/lib/api";
import { getToken } from "@/lib/auth";
import {
  collectModelAppearances,
  type ModelAppearance,
} from "@/lib/model-appearances";
import {
  directoryPrice,
  formatModalities,
  loadModelPin,
  modalityBadges,
  modelModalities,
} from "@/lib/model-pin";
import { formatScore } from "@/lib/utils";


export function ModelDetailPage() {
  const { modelId: rawId } = useParams();
  const canonical = decodeDatasetId(rawId || "");
  const pin = loadModelPin();
  const info = pin.models[canonical];
  const lab = info?.lab || canonical.split("/")[0] || "";
  const token = getToken();
  const [appearances, setAppearances] = useState<ModelAppearance[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void collectModelAppearances(token)
      .then((rows) => {
        if (cancelled) return;
        setAppearances(rows.filter((row) => row.canonical === canonical));
      })
      .catch(() => {
        if (!cancelled) setAppearances([]);
      });
    return () => {
      cancelled = true;
    };
  }, [canonical, token]);

  const price = useMemo(
    () => directoryPrice(canonical, canonical, pin),
    [canonical, pin],
  );

  if (!info) {
    return (
      <>
        <CatalogHead
          title="Models"
          crumbs={[{ label: "Models", href: "/models" }, { label: canonical || "Unknown" }]}
        />
        <EmptyState
          icon={Boxes}
          glyph="models"
          title="Unknown model"
          caption="No pin row for this id. Overlay invoke ids still run as written."
        />
      </>
    );
  }

  const badges = modalityBadges(modelModalities(info));

  return (
    <>
      <CatalogHead
        title="Models"
        crumbs={[
          { label: "Models", href: "/models" },
          { label: info.name },
        ]}
      />
      <div className="space-y-6">
        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <LabMark lab={lab} size={22} />
            <h2 className="text-sm font-medium text-ink">{info.name}</h2>
            <ModalityMarks kinds={badges} />
            <span className="text-sm text-body">{pin.labs[lab]?.name || lab}</span>
          </div>
          <p className="text-sm text-body">{info.description || "No description in the pin."}</p>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
            <Fact label="Canonical" value={canonical} />
            <Fact label="Family" value={info.family || "—"} />
            <Fact label="Released" value={info.release_date || "—"} />
            <Fact
              label="Context"
              value={
                info.context != null
                  ? `${info.context.toLocaleString()} tok`
                  : "—"
              }
            />
            <Fact
              label="Directory price"
              value={
                price
                  ? `$${price.input} / $${price.output} per MTok (${price.provider})`
                  : "—"
              }
            />
            <Fact label="Open weights" value={info.open_weights ? "yes" : "no"} />
            <Fact label="Modalities" value={formatModalities(modelModalities(info))} />
            <Fact
              label="Capabilities"
              value={[
                info.reasoning ? "reasoning" : null,
                info.tool_call ? "tools" : null,
                info.attachment ? "attachments" : null,
              ]
                .filter(Boolean)
                .join(", ") || "—"}
            />
            <Fact
              label="Weights"
              value={info.weights || "—"}
            />
          </dl>
          <p className="text-xs text-mute">
            Directory price is the pin snapshot, not this suite’s bill, and not PASS.
          </p>
        </section>

        <section className="space-y-2">
          <h2 className="text-sm font-medium text-ink">Appearances</h2>
          {appearances === null ? (
            <p className="text-sm text-body">Loading appearances…</p>
          ) : appearances.length === 0 ? (
            <p className="text-sm text-body">No consented Agent Performance yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Harness</TableHead>
                  <TableHead>Dataset</TableHead>
                  <TableHead>Overlay</TableHead>
                  <TableHead className="text-right">Pass</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {appearances.map((row) => (
                  <TableRow key={`${row.packageId}:${row.suiteRunId}:${row.overlay}`}>
                    <TableCell>
                      <Link
                        to={agentPackageHref(row.packageId, row.overlay)}
                        className="text-link hover:text-link-deep"
                      >
                        {row.packageId}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/datasets/${encodeDatasetId(row.datasetId)}?tab=leaderboard&suite=${encodeURIComponent(row.suiteRunId)}`}
                        className="text-link hover:text-link-deep"
                      >
                        {row.datasetId}
                      </Link>
                    </TableCell>
                    <TableCell className="text-body">{row.overlay}</TableCell>
                    <TableCell className="text-right">
                      {row.passRate != null ? (
                        <ScoreRing value={row.passRate}>
                          {formatScore(row.passRate)}
                        </ScoreRing>
                      ) : (
                        <span className="text-mute">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </section>
      </div>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-mute">{label}</dt>
      <dd className="text-sm text-ink break-all">{value}</dd>
    </div>
  );
}
