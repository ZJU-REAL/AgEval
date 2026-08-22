import { useEffect } from "react";

export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = `${title} · ageval Viewer`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
