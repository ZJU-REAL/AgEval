/** Browser-local token storage for Hub login (never written to packages/evidence). */

const TOKEN_KEY = "bora-hub-registry-token";
const USER_KEY = "bora-hub-github-user";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string, githubUser?: string | null): void {
  localStorage.setItem(TOKEN_KEY, token);
  if (githubUser) {
    localStorage.setItem(USER_KEY, githubUser);
  }
}

export function getGithubUser(): string | null {
  try {
    return localStorage.getItem(USER_KEY);
  } catch {
    return null;
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}
