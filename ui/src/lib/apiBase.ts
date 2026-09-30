// apiBase: the ranch dashboard is served separately from herd, so API calls
// need an explicit base. Set VITE_HERD_API at build time
// (e.g. VITE_HERD_API=http://127.0.0.1:25100), or window.__HERD_API__ at
// runtime. Empty (default) = same origin, the old embedded behaviour.
declare global {
  interface Window {
    __HERD_API__?: string;
  }
}

const fromWindow =
  typeof window !== "undefined" && window.__HERD_API__ ? window.__HERD_API__ : "";

const fromEnv =
  (import.meta as unknown as { env?: Record<string, string | undefined> }).env
    ?.VITE_HERD_API ?? "";

export const API_BASE = (fromWindow || fromEnv).replace(/\/+$/, "");

/** Prefix a herd API path with the configured base. */
export const api = (path: string): string => `${API_BASE}${path}`;
