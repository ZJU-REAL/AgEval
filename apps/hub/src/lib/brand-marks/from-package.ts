import type { PackageRelease } from "@/lib/api";
import {
  resolveEntityMark,
  type EntityMarkHint,
} from "@/lib/brand-marks/resolve";

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function entityHintFromPackage(
  row: PackageRelease,
  kind?: "plugin" | "agent",
): EntityMarkHint {
  const slots: string[] = [];
  const preview = row.plugin_preview;
  if (preview) {
    for (const id of [
      ...(preview.slots?.exclusive ?? []),
      ...(preview.slots?.chain ?? []),
      ...(preview.declared ?? []).map((slot) => slot.id),
    ]) {
      if (id?.trim()) slots.push(id.trim());
    }
  }
  const binding = row.agent_preview?.binding;
  return {
    iconKey: row.icon_key,
    packageId: row.dataset_id,
    displayName: row.display_name || row.agent_preview?.label || null,
    slots: kind === "agent" ? [] : slots,
    entry: asString(
      binding && typeof binding === "object"
        ? (binding.options as { entry?: unknown } | undefined)?.entry
        : null,
    ),
  };
}

export function markFromPackage(
  row: PackageRelease,
  kind?: "plugin" | "agent",
) {
  return resolveEntityMark(entityHintFromPackage(row, kind));
}
