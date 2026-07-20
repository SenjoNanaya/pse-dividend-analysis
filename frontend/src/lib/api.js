/**
 * API origin for fetch().
 * - unset / empty: same-origin (Vite `/api` proxy, Django-served SPA, Cloudflare Tunnel)
 * - set (e.g. Vercel): absolute origin such as https://edge-api.onrender.com
 */
const raw = import.meta.env.VITE_API_BASE;
const API_ORIGIN =
  raw === undefined || raw === null || String(raw).trim() === ''
    ? ''
    : String(raw).replace(/\/$/, '');

export const API_BASE = `${API_ORIGIN}/api/companies`;
export const FACETS_URL = `${API_BASE}/facets/`;
export const jsonHeaders = { Accept: 'application/json' };
