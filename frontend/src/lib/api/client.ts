const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const TOKEN_KEY = "memoryops_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  return sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAccessToken();

  const headers = new Headers(options.headers);

  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const fullUrl = `${API_BASE_URL}${url}`;

  const res = await fetch(fullUrl, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errMsg = `Request failed with status ${res.status}`;

    try {
      const errBody = await res.json();

      if (errBody?.error?.message) {
        errMsg = errBody.error.message;
      } else if (errBody?.detail) {
        errMsg = errBody.detail;
      }
    } catch {
      // ignore
    }

    throw new Error(errMsg);
  }

  return res.json() as Promise<T>;
}