import { toast } from "sonner";

const TOKEN_KEY = "fa_token";

// empty in dev (Vite proxies /api to the local server), the Render URL in production
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

export function apiUrl(path: string): string {
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// the free Render server sleeps when nobody uses it and takes about a minute to wake up
let wakeNoticeShown = false;

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {});
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const slow = window.setTimeout(() => {
    if (wakeNoticeShown) return;
    wakeNoticeShown = true;
    toast.message("Waking up the server…", { description: "On the free plan this can take up to a minute." });
  }, 5000);
  try {
    return await fetch(apiUrl(path), { ...init, headers });
  } finally {
    window.clearTimeout(slow);
  }
}

export async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* ignore */
  }
  return fallback;
}
