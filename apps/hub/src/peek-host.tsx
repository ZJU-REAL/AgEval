import { FrameModal } from "@/components/frame-modal";
import { HubRoutes } from "@/hub-routes";
import { PeekRouter } from "@/peek-router";

export type PeekTarget =
  | { type: "dataset"; datasetId: string; search?: string }
  | { type: "user"; login: string };

export function peekToPath(peek: PeekTarget): string {
  if (peek.type === "user") {
    return `/users/${encodeURIComponent(peek.login)}`;
  }
  const query = peek.search ? `?${peek.search.replace(/^\?/, "")}` : "";
  return `/datasets/${encodeURIComponent(peek.datasetId)}${query}`;
}

export function PeekHost({
  peek,
  onClose,
}: {
  peek: PeekTarget;
  onClose: () => void;
}) {
  const initial = peekToPath(peek);
  return (
    <PeekRouter initial={initial} key={initial}>
      <FrameModal open title="Preview" onClose={onClose}>
        <HubRoutes includeWorkspace={false} />
      </FrameModal>
    </PeekRouter>
  );
}
