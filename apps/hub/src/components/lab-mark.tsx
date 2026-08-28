import { useState } from "react";

import { labLogoSrc, loadModelPin } from "@/lib/model-pin";
import { cn } from "@/lib/utils";

function LetterMark({
  letter,
  size,
  className,
  title,
}: {
  letter: string;
  size: number;
  className?: string;
  title?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-canvas-soft font-medium text-mute",
        className,
      )}
      title={title}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.48) }}
      aria-hidden
    >
      {letter}
    </span>
  );
}

export function LabMark({
  lab,
  size = 20,
  className,
  title,
}: {
  lab: string;
  size?: number;
  className?: string;
  title?: string;
}) {
  const [broken, setBroken] = useState(false);
  const id = lab.trim();
  const pin = loadModelPin();
  const name = pin.labs[id]?.name || id;
  const src = id ? labLogoSrc(id) : "";
  const letter = (name || id || "?").slice(0, 1).toUpperCase();

  if (!src || broken) {
    return (
      <LetterMark letter={letter} size={size} className={className} title={title || name} />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-canvas-soft p-0.5",
        className,
      )}
      title={title || name}
      style={{ width: size, height: size }}
    >
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        className="h-full w-full object-contain"
        onError={() => setBroken(true)}
      />
    </span>
  );
}
