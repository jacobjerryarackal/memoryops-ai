const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function request<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${url}`, options);

  if (!res.ok) {
    let errMsg = `Request failed with status ${res.status}`;

    try {
      const errBody = await res.json();

      if (errBody?.error?.message) {
        errMsg = errBody.error.message;
      }
    } catch {
      // ignore
    }

    throw new Error(errMsg);
  }

  return res.json() as Promise<T>;
}