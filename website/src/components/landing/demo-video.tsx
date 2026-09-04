"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { assetPath } from "@/lib/shared";

const VIDEO_ID = "MxiM9A9YvLc";

/** Official YouTube mark. Fill lives in the public SVG, not in TSX. */
function YoutubeMark() {
  return (
    <img
      src={assetPath("/images/youtube.svg")}
      alt=""
      width={16}
      height={16}
      draggable={false}
    />
  );
}

type DemoVideoProps = {
  className: string;
  /** Trigger text, e.g. "查看演示". */
  label: string;
  /** Accessible name for the dialog and the iframe. */
  title: string;
  closeLabel: string;
};

/**
 * "Watch demo" trigger plus a click-to-play lightbox. The page ships no
 * iframe; pressing the trigger mounts the nocookie player with autoplay,
 * and closing it (X, backdrop, Escape) unmounts playback.
 *
 * The stage's backdrop-filter makes it a containing block for fixed
 * descendants, so the lightbox must portal to <body> to cover the viewport.
 */
export function DemoVideo({ className, label, title, closeLabel }: DemoVideoProps) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        type="button"
        ref={triggerRef}
        className={className}
        onClick={() => setOpen(true)}
      >
        <YoutubeMark />
        {label}
      </button>
      {open
        ? createPortal(
            <div
              className="ageval-landing demo-lightbox"
              role="dialog"
              aria-modal="true"
              aria-label={title}
              onClick={close}
            >
              <div
                className="demo-lightbox-panel"
                onClick={(event) => event.stopPropagation()}
              >
                <iframe
                  src={`https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1&rel=0`}
                  title={title}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                />
                <button type="button" className="demo-lightbox-close" onClick={close} autoFocus>
                  <X aria-hidden="true" />
                  {closeLabel}
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
