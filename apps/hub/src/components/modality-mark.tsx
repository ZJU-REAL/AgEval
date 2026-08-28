import {
  AudioLines,
  ClosedCaption,
  Image,
  LayoutGrid,
  Type,
  Video,
  type LucideIcon,
} from "lucide-react";

import type { ModalityKind, ModalityTab } from "@/lib/model-pin/modalities";
import { cn } from "@/lib/utils";

const ICONS: Record<ModalityKind, LucideIcon> = {
  text: Type,
  image: Image,
  video: Video,
  transcription: ClosedCaption,
  speech: AudioLines,
};

const TONE: Record<ModalityKind, { fg: string; plate: string }> = {
  text: { fg: "text-mod-text", plate: "bg-mod-text-soft" },
  image: { fg: "text-mod-image", plate: "bg-mod-image-soft" },
  video: { fg: "text-mod-video", plate: "bg-mod-video-soft" },
  transcription: { fg: "text-mod-transcription", plate: "bg-mod-transcription-soft" },
  speech: { fg: "text-mod-speech", plate: "bg-mod-speech-soft" },
};

export const MODALITY_TAB_META: {
  id: ModalityTab;
  label: string;
  icon: LucideIcon;
  iconClassName?: string;
}[] = [
  {
    id: "all",
    label: "All",
    icon: LayoutGrid,
    iconClassName: "text-mute group-hover:text-ink group-aria-selected:text-ink",
  },
  {
    id: "text",
    label: "Text",
    icon: Type,
    iconClassName: "text-mute group-hover:text-mod-text group-aria-selected:text-mod-text",
  },
  {
    id: "image",
    label: "Image",
    icon: Image,
    iconClassName: "text-mute group-hover:text-mod-image group-aria-selected:text-mod-image",
  },
  {
    id: "video",
    label: "Video",
    icon: Video,
    iconClassName: "text-mute group-hover:text-mod-video group-aria-selected:text-mod-video",
  },
  {
    id: "transcription",
    label: "Transcription",
    icon: ClosedCaption,
    iconClassName:
      "text-mute group-hover:text-mod-transcription group-aria-selected:text-mod-transcription",
  },
  {
    id: "speech",
    label: "Speech",
    icon: AudioLines,
    iconClassName: "text-mute group-hover:text-mod-speech group-aria-selected:text-mod-speech",
  },
];

export function ModalityMark({
  kind,
  className,
}: {
  kind: ModalityKind;
  className?: string;
}) {
  const Icon = ICONS[kind];
  const tone = TONE[kind];
  const label = MODALITY_TAB_META.find((item) => item.id === kind)?.label || kind;
  return (
    <span
      className={cn(
        "inline-flex size-6 shrink-0 items-center justify-center rounded-[8px]",
        tone.plate,
        className,
      )}
      title={label}
      aria-label={label}
    >
      <Icon className={cn("size-3.5", tone.fg)} aria-hidden />
    </span>
  );
}

export function ModalityMarks({
  kinds,
  className,
}: {
  kinds: ModalityKind[];
  className?: string;
}) {
  if (kinds.length === 0) return null;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {kinds.map((kind) => (
        <ModalityMark key={kind} kind={kind} />
      ))}
    </span>
  );
}
