import { useEffect, useRef } from "react";

type Props = {
  checked: boolean;
  indeterminate?: boolean;
  label: string;
  onChange: (next: boolean) => void;
};

export function JobCheck({ checked, indeterminate, label, onChange }: Props) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = Boolean(indeterminate);
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      aria-label={label}
      className="h-3.5 w-3.5 shrink-0 rounded-[3px] border-hairline accent-ink"
      onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      onChange={(e) => {
        e.stopPropagation();
        onChange(e.target.checked);
      }}
    />
  );
}
