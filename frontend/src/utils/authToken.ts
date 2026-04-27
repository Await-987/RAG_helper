import { safeSessionStorage } from './browserStorage';

const ACCESS_TOKEN_KEY = 'access_token';

export function getAccessToken(): string | null {
  return safeSessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  safeSessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  safeSessionStorage.removeItem(ACCESS_TOKEN_KEY);
}
