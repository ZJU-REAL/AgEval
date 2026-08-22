import type { PackageRelease } from "@/lib/api";
import { resolveEntityMark, type EntityMarkHint } from "@/lib/brand-marks/resolve";

export function entityHintFromPackage(row: PackageRelease): EntityMarkHint {
  return {
    iconKey: row.icon_key,
    iconGithub: row.icon_github,
    uploadedBy: row.uploaded_by,
    displayName: row.display_name || row.agent_preview?.label || null,
    packageId: row.dataset_id,
  };
}

export function markFromPackage(row: PackageRelease) {
  return resolveEntityMark(entityHintFromPackage(row));
}
