import { useEffect, useState } from "react";

import { getUser, type UserPublic } from "@/lib/api";

export function usePublicUser(login: string | null | undefined): UserPublic | null {
  const [user, setUser] = useState<UserPublic | null>(null);

  useEffect(() => {
    const id = (login || "").trim();
    if (!id) {
      setUser(null);
      return;
    }
    let cancelled = false;
    getUser(id)
      .then((row) => {
        if (!cancelled) setUser(row);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [login]);

  return user;
}
