export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
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
