export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export async function api<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try { response = await fetch(`${API_URL}${path}`, { ...init, headers }); }
  catch { throw new Error("Cannot reach the server. Please check that the backend is running."); }
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(data?.error?.message ?? "Request failed. Please try again.");
  return data as T;
}
