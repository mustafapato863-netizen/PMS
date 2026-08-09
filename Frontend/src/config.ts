/**
 * Central API configuration
 * All hooks import API_BASE and SOCKET_URL from here
 */

const browserOrigin = typeof window !== 'undefined' ? window.location.origin : '';
const configuredApiBase = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL;
const apiBase = configuredApiBase?.trim() || (
  import.meta.env.PROD ? browserOrigin : 'http://127.0.0.1:8000'
);

// Accept a hostname copied from Vercel settings, but always make the request
// target absolute so it cannot be interpreted as a path on the frontend host.
export const API_BASE = (
  !apiBase || /^https?:\/\//i.test(apiBase) ? apiBase : `https://${apiBase}`
).replace(/\/+$/, '');

export const SOCKET_URL = import.meta.env.VITE_SOCKET_URL?.trim() || (
  import.meta.env.PROD ? (API_BASE || browserOrigin) : 'ws://127.0.0.1:8000'
);

export const REALTIME_ENABLED = (
  import.meta.env.VITE_REALTIME_ENABLED ?? (import.meta.env.PROD ? 'false' : 'true')
).trim().toLowerCase() === 'true';

export const API_TIMEOUT_MS = 30_000;

