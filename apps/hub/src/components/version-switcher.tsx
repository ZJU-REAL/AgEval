import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { versionLabel, type PackageRelease } from "@/lib/api";

export function VersionSwitcher({
  versions,
  value,
  onChange,
}: {
  versions: PackageRelease[];
  value: string;
  onChange: (version: string) => void;
}) {
  if (versions.length === 0) return null;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label="Package version" className="min-w-[11rem]">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {versions.map((row) => (
          <SelectItem key={row.version} value={row.version}>
            {versionLabel(row)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
