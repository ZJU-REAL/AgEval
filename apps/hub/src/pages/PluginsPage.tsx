import { Puzzle } from "lucide-react";

import { Shell } from "@/components/layout";

/**
 * Spec 06 Phase 0 shell — Plugin marketplace list.
 * Phase 2 fills list/detail against Registry package_kind=plugin.
 */
export function PluginsPage() {
  return (
    <Shell>
      <div className="mb-4">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Plugin marketplace
        </h1>
        <p className="text-sm text-body mt-1">
          Browse <span className="font-mono text-xs">bora.plugin/1</span>{" "}
          packages on this Registry. Install is CLI-only (Recognition only —
          does not change profiles).
        </p>
      </div>

      <div className="rounded-[8px] border border-dashed border-hairline bg-canvas-soft p-10 text-center text-sm text-body">
        <div className="flex justify-center mb-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-[12px] bg-canvas border border-hairline text-mute">
            <Puzzle className="h-8 w-8" strokeWidth={1.5} aria-hidden />
          </div>
        </div>
        <p className="font-medium text-ink">Marketplace shell</p>
        <p className="mt-1 text-mute max-w-md mx-auto">
          Route is live. List and detail load in Spec 06 Phase 2 once{" "}
          <span className="font-mono text-xs">package_kind</span> is exposed on
          package list/meta (Phase 1 if needed).
        </p>
      </div>
    </Shell>
  );
}
