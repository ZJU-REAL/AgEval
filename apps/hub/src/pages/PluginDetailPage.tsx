import { Link, useParams } from "react-router-dom";

import { BreadcrumbNav } from "@/components/breadcrumb";
import { Shell } from "@/components/layout";
import { decodeDatasetId } from "@/lib/api";

/**
 * Spec 06 Phase 0 shell — Plugin marketplace detail.
 * Phase 2: badge, slots, files, install command.
 */
export function PluginDetailPage() {
  const { pluginId: rawId } = useParams();
  const pluginId = decodeDatasetId(rawId || "");

  return (
    <Shell>
      <BreadcrumbNav
        items={[
          { label: "Plugin marketplace", href: "/plugins" },
          { label: pluginId || "…" },
        ]}
        className="mb-4"
      />
      <div className="mb-4">
        <h1 className="text-xl font-semibold tracking-tight text-ink font-mono">
          {pluginId || "—"}
        </h1>
        <p className="text-sm text-mute mt-1">
          Detail shell — slots, files, and install command land in Phase 2.
        </p>
      </div>
      <p className="text-sm text-body">
        <Link to="/plugins" className="underline underline-offset-2">
          ← Back to marketplace
        </Link>
      </p>
    </Shell>
  );
}
