import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  deletePackageRelease,
  isDraftRelease,
  releasePackageDraft,
  setPackageVisibility,
  type PackageRelease,
  RegistryHttpError,
} from "@/lib/api";

export function PackageOwnerOps({
  packageId,
  release,
  canManage,
  token,
  onUpdated,
  onDeleted,
  onReleased,
}: {
  packageId: string;
  release: PackageRelease;
  canManage: boolean;
  token: string | null;
  onUpdated: (next: PackageRelease) => void;
  onDeleted: () => void;
  onReleased: (next: PackageRelease) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [releaseOpen, setReleaseOpen] = useState(false);
  const [releaseVisibility, setReleaseVisibility] = useState<
    "public" | "private"
  >(release.visibility === "public" ? "public" : "private");
  const [releaseVersion, setReleaseVersion] = useState("");
  const [replace, setReplace] = useState(false);
  const draft = isDraftRelease(release);

  if (!canManage || !token) return null;

  function fail(err: unknown) {
    if (err instanceof RegistryHttpError) {
      setError(`${err.code}: ${err.message}`);
    } else {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function changeVisibility(next: "public" | "private") {
    if (next === release.visibility) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await setPackageVisibility(
        packageId,
        release.version,
        next,
        token,
      );
      onUpdated({ ...release, ...updated, visibility: next });
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deletePackageRelease(packageId, release.version, token);
      onDeleted();
    } catch (err) {
      fail(err);
      setConfirmDelete(false);
    } finally {
      setBusy(false);
    }
  }

  async function promote() {
    setBusy(true);
    setError(null);
    try {
      const updated = await releasePackageDraft(
        packageId,
        {
          visibility: releaseVisibility,
          version: releaseVersion.trim() || undefined,
          replace: replace || undefined,
        },
        token,
      );
      setReleaseOpen(false);
      onReleased(updated);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {draft ? (
          <Button
            type="button"
            size="sm"
            disabled={busy}
            onClick={() => {
              setReleaseOpen(true);
              setError(null);
              setReleaseVisibility(
                release.visibility === "public" ? "public" : "private",
              );
            }}
          >
            Release draft
          </Button>
        ) : (
          <Select
            value={release.visibility === "public" ? "public" : "private"}
            onValueChange={(value) => {
              if (value === "public" || value === "private") {
                void changeVisibility(value);
              }
            }}
            disabled={busy}
          >
            <SelectTrigger
              aria-label="Package visibility"
              className="h-8 min-w-0 w-auto font-mono text-xs"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="public">public</SelectItem>
              <SelectItem value="private">private</SelectItem>
            </SelectContent>
          </Select>
        )}
        <Button
          type="button"
          size="sm"
          variant={confirmDelete ? "default" : "outline"}
          disabled={busy}
          onClick={() => void remove()}
        >
          {confirmDelete ? "Confirm delete" : "Delete version"}
        </Button>
        {confirmDelete ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => setConfirmDelete(false)}
          >
            Cancel
          </Button>
        ) : null}
      </div>
      {error ? <p className="text-xs font-mono text-error">{error}</p> : null}

      {releaseOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="release-draft-title"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setReleaseOpen(false);
          }}
        >
          <div className="w-full max-w-md rounded-[12px] border border-hairline bg-canvas shadow-lg p-5 space-y-4">
            <div>
              <h2
                id="release-draft-title"
                className="text-lg font-semibold tracking-tight text-ink"
              >
                Release draft
              </h2>
              <p className="text-sm text-mute mt-1">
                Promote the current draft slot to a numbered release. Leave
                version empty to take it from the package archive.
              </p>
            </div>
            <div>
              <label
                htmlFor="release-version"
                className="text-xs font-medium text-mute uppercase tracking-wide"
              >
                Version
              </label>
              <Input
                id="release-version"
                value={releaseVersion}
                onChange={(e) => setReleaseVersion(e.target.value)}
                placeholder="from archive"
                disabled={busy}
                className="mt-1.5 font-mono text-sm"
              />
            </div>
            <div>
              <p className="text-xs font-medium text-mute uppercase tracking-wide">
                Visibility
              </p>
              <Select
                value={releaseVisibility}
                onValueChange={(value) => {
                  if (value === "public" || value === "private") {
                    setReleaseVisibility(value);
                  }
                }}
                disabled={busy}
              >
                <SelectTrigger className="mt-1.5 h-9 min-w-0 w-full font-mono text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="private">private</SelectItem>
                  <SelectItem value="public">public</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <label className="flex items-center gap-2 text-sm text-body">
              <input
                type="checkbox"
                checked={replace}
                disabled={busy}
                onChange={(e) => setReplace(e.target.checked)}
              />
              Replace if this version already exists
            </label>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={busy}
                onClick={() => setReleaseOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={busy}
                onClick={() => void promote()}
              >
                {busy ? "Releasing…" : "Release"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
