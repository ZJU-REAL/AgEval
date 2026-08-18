import type { Trial } from "@/lib/api";
import { formatModelLabel } from "@/lib/utils";

export type ActorRow = NonNullable<Trial["actors"]>[number];

export function actorLabel(a: ActorRow | undefined, profileId: string): string {
  if (!a) return profileId;
  const bits = [a.role || profileId];
  if (a.agent) bits.push(String(a.agent));
  if (a.model) bits.push(formatModelLabel(a.model, a.reasoning_effort).text);
  return bits.join(" · ");
}
