import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { loadModelPin } from "@/lib/model-pin";

const NONE = "__none__";

export function CanonicalSelect({
  value,
  onChange,
  hits,
  allowEmpty,
  disabled,
  includePin,
  label = "Model",
}: {
  value: string;
  onChange: (next: string) => void;
  hits: string[];
  allowEmpty?: boolean;
  disabled?: boolean;
  includePin?: boolean;
  label?: string;
}) {
  const pin = loadModelPin();
  const chosen = value.trim();
  const hitSet = new Set(hits.filter(Boolean));
  const extras = includePin
    ? Object.keys(pin.models).filter((id) => !hitSet.has(id)).sort()
    : [];

  return (
    <Select
      value={chosen || NONE}
      onValueChange={(next) => onChange(next === NONE ? "" : next)}
      disabled={disabled}
    >
      <SelectTrigger aria-label={label} className="h-8 min-w-0 w-auto shrink-0 text-xs">
        <SelectValue placeholder="Model" />
      </SelectTrigger>
      <SelectContent>
        {allowEmpty ? (
          <SelectItem value={NONE} mono={false}>
            None
          </SelectItem>
        ) : null}
        {hits.map((id) => (
          <SelectItem key={id} value={id} mono={false} trailing={pin.models[id]?.lab}>
            {pin.models[id]?.name || id}
          </SelectItem>
        ))}
        {extras.map((id) => (
          <SelectItem key={id} value={id} mono={false} trailing={pin.models[id]?.lab}>
            {pin.models[id]?.name || id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
