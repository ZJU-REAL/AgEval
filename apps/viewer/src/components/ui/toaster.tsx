import { useEffect, useState } from "react";

import { bindToast, type ToastInput } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

type ToastItem = ToastInput & { id: number; leaving?: boolean };

let seed = 0;

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const timers = new Map<number, number>();
    bindToast((input) => {
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
    });
    return () => {
      bindToast(null);
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
