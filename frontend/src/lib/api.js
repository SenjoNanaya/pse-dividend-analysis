const API_ORIGIN = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(
  /\/$/,
  '',
);

export const API_BASE = `${API_ORIGIN}/api/companies`;
export const FACETS_URL = `${API_BASE}/facets/`;
export const jsonHeaders = { Accept: 'application/json' };
