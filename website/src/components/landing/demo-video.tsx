"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

const VIDEO_ID = "MxiM9A9YvLc";

/** Official YouTube mark (simple-icons geometry): red plate, white triangle. */
function YoutubeMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        fillRule="evenodd"
        fill="#ff0000"
        d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"
      />
      <path fill="#ffffff" d="M9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
    </svg>
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
