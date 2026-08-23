import type { PackageRelease } from "@/lib/api";
import { parseGithubLogin } from "@/lib/brand-marks/github";
import { resolveEntityMark, type EntityMarkHint, type ResolvedMark } from "@/lib/brand-marks/resolve";
import { githubRepoUrl } from "@/lib/public-links";

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

/** Same GitHub identity as the sidebar link (`githubRepoUrl`, default ZJU-REAL/ageval). */
export function markFromGithubRepoLink(): ResolvedMark {
  const login = parseGithubLogin(githubRepoUrl()) || "ZJU-REAL";
  return resolveEntityMark({ iconGithub: login });
}
