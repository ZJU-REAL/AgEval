export type SlotHistoryEntry = {
  run_id?: string | null;
  status?: string | null;
};

export function SlotHistorySelect({
  viewingRunId,
  currentRunId,
  previous,
  onSelect,
}: {
  viewingRunId: string;
  currentRunId: string | null | undefined;
  previous: SlotHistoryEntry[] | undefined;
  onSelect: (runId: string) => void;
}) {
  const items = previous?.filter((p) => p.run_id) ?? [];
  if (!currentRunId || items.length === 0) return null;

  return (
    <label className="flex items-center gap-2 text-xs text-mute shrink-0">
      <span>Version</span>
      <select
        className="max-w-[28ch] rounded-[6px] border border-hairline bg-canvas px-2 py-1 font-mono text-[12px] text-ink"
        value={viewingRunId}
        onChange={(e) => onSelect(e.target.value)}
        aria-label="Slot version"
      >
        <option value={currentRunId}>current · {currentRunId}</option>
        {[...items].reverse().map((item) => (
          <option key={item.run_id!} value={item.run_id!}>
            {item.status ? `${item.status} · ` : ""}
            {item.run_id}
          </option>
        ))}
      </select>
    </label>
  );
}
