import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Trial } from "@/lib/api";

/** Actors: Role | Agent | Model | Time | Usage — observational ≠ PASS */
export function ActorsTable({ actors }: { actors: NonNullable<Trial["actors"]> }) {
  if (actors.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <div className="rounded-[8px] border border-hairline overflow-hidden overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Role</TableHead>
              <TableHead>Agent</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Usage</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {actors.map((a) => (
              <TableRow key={a.profile_id || `${a.role}-${a.agent}`}>
                <TableCell className="font-medium font-mono text-[13px]">
                  {a.role}
                </TableCell>
                <TableCell className="font-mono text-[13px] text-body">
                  {a.agent}
                </TableCell>
                <TableCell className="font-mono text-[13px] text-mute">
                  {a.model || "-"}
                </TableCell>
                <TableCell className="font-mono text-[13px] tabular text-body">
                  {a.time_label || "-"}
                </TableCell>
                <TableCell
                  className="font-mono text-[12px] text-mute max-w-[36ch]"
                  title={
                    a.usage_label
                      ? "Observational usage (tokens/cost); not PASS authority. Cache hit = cached_read / input when present. Session-last invoke for cumulative fields."
                      : undefined
                  }
                >
                  {a.usage_label || "-"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-[11px] text-mute">
        Time sums inv latency. Usage is last-invoke session snapshot
        (tokens/cost); trajectory and usage are not PASS.
      </p>
    </div>
  );
}
