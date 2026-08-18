/**
 * Flat-crown owl (owl-v2 plate). Color via `currentColor` unless the
 * variant fixes a brand pair (plates, watermarks).
 */

type OwlFlatProps = { className?: string };

const BODY_PATH =
  "M 156 258 C 200 385 248 585 276 720 C 278 1020 190 1680 72 2218 C 50 2262 48 2294 118 2268 C 300 2210 545 1990 662 1720 C 705 1570 590 1455 512 1408 C 488 1384 508 1382 548 1420 C 700 1520 810 1720 796 1900 C 784 2060 690 2180 648 2214 C 622 2236 655 2258 735 2234 C 1100 2130 1420 1840 1500 1480 C 1526 1360 1518 1296 1494 1268 C 1480 1250 1462 1256 1446 1278 C 1340 1430 1140 1518 920 1496 C 720 1474 600 1260 548 1060 C 510 880 518 750 568 680 C 620 610 780 638 980 720 C 1160 795 1270 930 1298 1070 C 1314 1155 1316 1172 1310 1184 C 1302 1198 1330 1190 1362 1148 C 1480 980 1570 720 1548 480 C 1535 300 1400 175 1260 198 C 1205 188 1165 208 1095 210 C 820 210 520 210 300 210 C 235 210 188 206 168 228 C 150 214 136 222 156 258 Z";

const EYE_PATH =
  "M 1050.5 1003 H 1187.5 A 34.5 34.5 0 0 1 1222.0 1037.5 A 34.5 34.5 0 0 1 1187.5 1072.0 H 1050.5 A 34.5 34.5 0 0 1 1016.0 1037.5 A 34.5 34.5 0 0 1 1050.5 1003 Z";

const CHEVRON_PATH = "M 730 880 L 930 1021 L 730 1163";

function OwlFlatGlyph({
  fill,
  fillOpacity,
}: {
  fill: string;
  fillOpacity?: number;
}) {
  return (
    <>
      <g fill={fill} fillOpacity={fillOpacity}>
        <path d={BODY_PATH} />
        <path d={EYE_PATH} />
      </g>
      <path
        d={CHEVRON_PATH}
        fill="none"
        stroke={fill}
        strokeWidth={76}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeOpacity={fillOpacity}
      />
    </>
  );
}

/** Full body, `currentColor` (`mark-flat.svg`). */
export function OwlFlatMark({ className }: OwlFlatProps) {
  return (
    <svg
      className={className}
      viewBox="20 60 1580 2300"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <OwlFlatGlyph fill="currentColor" />
    </svg>
  );
}

/** Full body, `currentColor` (`mark-flat.svg` geometry). */
export function OwlFlatIcon({ className }: OwlFlatProps) {
  return (
    <svg
      className={className}
      viewBox="20 60 1580 2300"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <OwlFlatGlyph fill="currentColor" />
    </svg>
  );
}

/** Head crop at the wing root, `currentColor` (`peek-flat.svg`). */
export function OwlFlatPeek({ className }: OwlFlatProps) {
  return (
    <svg
      className={className}
      viewBox="40 60 1540 1320"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <OwlFlatGlyph fill="currentColor" />
    </svg>
  );
}

const PLATE_PAIRS = {
  paper: { bg: "#212121", fg: "#F6EDDB" },
  cream: { bg: "#212121", fg: "#E0D1BE" },
  ink: { bg: "#F6EDDB", fg: "#212121" },
  klein: { bg: "#002FA7", fg: "#F6EDDB" },
} as const;

export type OwlFlatPlateVariant = keyof typeof PLATE_PAIRS;

/** Owl on a background plate with fixed brand colors (`plate-flat*.svg`). */
export function OwlFlatPlate({
  className,
  variant = "paper",
}: OwlFlatProps & { variant?: OwlFlatPlateVariant }) {
  const { bg, fg } = PLATE_PAIRS[variant];
  return (
    <svg
      className={className}
      viewBox="0 0 1760 2400"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect x={0} y={0} width={1760} height={2400} fill={bg} />
      <OwlFlatGlyph fill={fg} />
    </svg>
  );
}

/** Full-body owl + BORA wordmark, `currentColor` (`lockup-flat.svg`). */
export function OwlFlatLockup({ className }: OwlFlatProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 560 160"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <svg x={30.5} y={8} width={99} height={144} viewBox="20 60 1580 2300">
        <OwlFlatGlyph fill="currentColor" />
      </svg>
      <text
        x={168}
        y={108}
        fill="currentColor"
        fontFamily="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
        fontSize={72}
        fontWeight={600}
        letterSpacing="0.14em"
      >
        BORA
      </text>
    </svg>
  );
}

/** Section-background wash: 7% ink, or 10% white when `inverse`. */
export function OwlFlatWatermark({
  className,
  inverse = false,
}: OwlFlatProps & { inverse?: boolean }) {
  const color = inverse ? "#FFFFFF" : "#212121";
  const opacity = inverse ? 0.1 : 0.07;
  return (
    <svg
      className={className}
      viewBox="20 60 1580 2300"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <OwlFlatGlyph fill={color} fillOpacity={opacity} />
    </svg>
  );
}
