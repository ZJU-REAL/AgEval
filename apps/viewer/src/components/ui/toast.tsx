import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Tone = "ok" | "error";

type ToastInput = {
  message: string;
  tone?: Tone;
  duration?: number;
};

type ToastItem = ToastInput & { id: number; leaving?: boolean };

let seed = 0;
let notify: ((input: ToastInput) => void) | null = null;

export function toast(message: string, opts?: Omit<ToastInput, "message">) {
  notify?.({ message, ...opts });
}

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const timers = new Map<number, number>();
    notify = (input) => {
      const id = ++seed;
      setItems((prev) => [...prev.slice(-2), { ...input, id }]);
      const hold = input.duration ?? 2400;
      const hide = window.setTimeout(() => {
        setItems((prev) =>
          prev.map((item) => (item.id === id ? { ...item, leaving: true } : item)),
        );
        const gone = window.setTimeout(() => {
          setItems((prev) => prev.filter((item) => item.id !== id));
          timers.delete(id);
        }, 200);
        timers.set(id, gone);
      }, hold);
      timers.set(id, hide);
    };
    return () => {
      notify = null;
      for (const timer of timers.values()) window.clearTimeout(timer);
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-6 z-[60] flex flex-col items-center gap-2 px-4"
      aria-live="polite"
      aria-relevant="additions"
    >
      {items.map((item) => (
        <div
          key={item.id}
          role="status"
          data-ageval-toast=""
          data-leaving={item.leaving ? "" : undefined}
          className={cn(
            "pointer-events-auto max-w-sm rounded-[12px] border border-hairline bg-canvas px-3 py-2 text-sm shadow-[var(--viewer-shadow-pop)]",
            item.tone === "error" ? "text-error" : "text-ink",
          )}
        >
          {item.message}
        </div>
      ))}
    </div>
  );
}
