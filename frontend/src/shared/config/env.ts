/**
 * Runtime configuration from Vite env vars (frontend/.env.local).
 * Empty API base URL = same origin: Vite proxies /api locally, Vercel rewrites it in production.
 */
export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
} as const;
