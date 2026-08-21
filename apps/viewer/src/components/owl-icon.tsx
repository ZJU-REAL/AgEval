import { cn } from "@/lib/utils";

/**
 * AGEVAL flat-crown owl mark (owl-v2, full body), fill and stroke use
 * currentColor.
 */
export function OwlIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="20 60 1580 2300"
      fill="none"
      aria-hidden="true"
      className={cn("shrink-0", className)}
    >
      <g fill="currentColor">
        <path d="M 156 258 C 200 385 248 585 276 720 C 278 1020 190 1680 72 2218 C 50 2262 48 2294 118 2268 C 300 2210 545 1990 662 1720 C 705 1570 590 1455 512 1408 C 488 1384 508 1382 548 1420 C 700 1520 810 1720 796 1900 C 784 2060 690 2180 648 2214 C 622 2236 655 2258 735 2234 C 1100 2130 1420 1840 1500 1480 C 1526 1360 1518 1296 1494 1268 C 1480 1250 1462 1256 1446 1278 C 1340 1430 1140 1518 920 1496 C 720 1474 600 1260 548 1060 C 510 880 518 750 568 680 C 620 610 780 638 980 720 C 1160 795 1270 930 1298 1070 C 1314 1155 1316 1172 1310 1184 C 1302 1198 1330 1190 1362 1148 C 1480 980 1570 720 1548 480 C 1535 300 1400 175 1260 198 C 1205 188 1165 208 1095 210 C 820 210 520 210 300 210 C 235 210 188 206 168 228 C 150 214 136 222 156 258 Z" />
        <path d="M 1050.5 1003 H 1187.5 A 34.5 34.5 0 0 1 1222.0 1037.5 A 34.5 34.5 0 0 1 1187.5 1072.0 H 1050.5 A 34.5 34.5 0 0 1 1016.0 1037.5 A 34.5 34.5 0 0 1 1050.5 1003 Z" />
      </g>
      <path
        d="M 730 880 L 930 1021 L 730 1163"
        fill="none"
        stroke="currentColor"
        strokeWidth={76}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
