/** Browser-local token storage for Hub login (never written to packages/evidence). */

const TOKEN_KEY = "ageval-hub-registry-token";
const USER_KEY = "ageval-hub-github-user";
const NAME_KEY = "ageval-hub-github-name";
const AVATAR_KEY = "ageval-hub-github-avatar";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(
  token: string,
  githubUser?: string | null,
  githubName?: string | null,
  avatarUrl?: string | null,
): void {
  localStorage.setItem(TOKEN_KEY, token);
  if (githubUser) {
    localStorage.setItem(USER_KEY, githubUser);
  }
  if (githubName) {
    localStorage.setItem(NAME_KEY, githubName);
  } else {
    localStorage.removeItem(NAME_KEY);
  }
  if (avatarUrl) {
    localStorage.setItem(AVATAR_KEY, avatarUrl);
  } else if (githubUser) {
    // Fallback: GitHub avatar by login (works without stored avatar_url).
    localStorage.setItem(
      AVATAR_KEY,
      `https://github.com/${encodeURIComponent(githubUser)}.png?size=64`,
    );
  } else {
    localStorage.removeItem(AVATAR_KEY);
  }
}

export function getGithubUser(): string | null {
  try {
    return localStorage.getItem(USER_KEY);
  } catch {
    return null;
  }
}

export function getGithubName(): string | null {
  try {
    return localStorage.getItem(NAME_KEY);
  } catch {
    return null;
  }
}

export function getGithubAvatar(): string | null {
  try {
    return localStorage.getItem(AVATAR_KEY);
  } catch {
    return null;
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(NAME_KEY);
  localStorage.removeItem(AVATAR_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}
