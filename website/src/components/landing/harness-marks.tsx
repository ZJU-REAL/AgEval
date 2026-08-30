import type { SVGProps } from "react";
import { DSH_WHALE_PATH } from "./dsh-whale";

/**
 * Harness marks for the hero rotate line.
 *
 * `src` entries render official brand SVGs shared with the Hub
 * brand-marks catalog (`apps/hub/src/lib/brand-marks/assets/`, same
 * files and tone rules: ink marks sit on a white plate, color marks
 * render bare). DSH has no catalog asset yet, so it inlines the landing
 * whale path as currentColor.
 */

export type MarkProps = SVGProps<SVGSVGElement>;

type CatalogMark = {
  id: string;
  name: string;
  src: string;
  tone: "color" | "ink";
};

type InlineMark = {
  id: string;
  name: string;
  Mark: (props: MarkProps) => React.ReactElement;
};

export type Harness = CatalogMark | InlineMark;

export function DshMark(props: MarkProps) {
  return (
    <svg viewBox="0 0 512 509.64" aria-hidden="true" {...props}>
      <path fill="currentColor" fillRule="nonzero" d={DSH_WHALE_PATH} />
    </svg>
  );
}

export const HARNESSES: readonly Harness[] = [
  { id: "claude-code", name: "Claude Code", src: "/images/harness/claude-code.svg", tone: "color" },
  { id: "codex", name: "Codex", src: "/images/harness/codex.svg", tone: "color" },
  { id: "pi", name: "Pi", src: "/images/harness/pi.svg", tone: "ink" },
  { id: "opencode", name: "OpenCode", src: "/images/harness/opencode.svg", tone: "ink" },
  { id: "dsh", name: "DSH", Mark: DshMark },
  { id: "nooa", name: "NOOA", src: "/images/harness/nooa.svg", tone: "color" },
  { id: "miniswe", name: "mini-SWE-agent", src: "/images/harness/miniswe.svg", tone: "color" },
];
