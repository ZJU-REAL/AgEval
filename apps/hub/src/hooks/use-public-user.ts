import { useEffect, useState } from "react";

import { getUser, type UserPublic } from "@/lib/api";

let cachedLogin = "";
let cachedUser: UserPublic | null = null;

export function usePublicUser(login: string | null | undefined): UserPublic | null {
  const id = (login || "").trim();
  const [user, setUser] = useState<UserPublic | null>(() =>
    id && cachedLogin === id ? cachedUser : null,
  );

  useEffect(() => {
    if (!id) {
      cachedLogin = "";
      cachedUser = null;
      setUser(null);
      return;
    }
    if (cachedLogin === id) {
      setUser(cachedUser);
    }
    let cancelled = false;
    getUser(id)
      .then((row) => {
        if (cancelled) return;
        cachedLogin = id;
        cachedUser = row;
        setUser(row);
      })
      .catch(() => {
        if (cancelled) return;
        if (cachedLogin === id) {
          cachedLogin = "";
          cachedUser = null;
        }
        setUser(null);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return user;
}
