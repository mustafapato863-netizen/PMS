/**
 * Central API configuration
 * All hooks import API_BASE and SOCKET_URL from here
 */

const browserOrigin = typeof window !== 'undefined' ? window.location.origin : '';
const browserHostname = typeof window !== 'undefined' ? window.location.hostname : '';
const configuredApiBase = import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL;
const apiBase = configuredApiBase?.trim() || (
  import.meta.env.PROD ? browserOrigin : 'http://127.0.0.1:8000'
);

function alignLocalServiceHost(serviceUrl: string): string {
  const loopbackHosts = ['localhost', '127.0.0.1', '[::1]'];
  if (!import.meta.env.DEV || !loopbackHosts.includes(browserHostname)) return serviceUrl;

  try {
    const url = new URL(serviceUrl);
    // localhost and 127.0.0.1 are different cookie sites. Keep local services
    // on the page's hostname so SameSite refresh cookies survive a reload.
    if (loopbackHosts.includes(url.hostname) && url.hostname !== browserHostname) {
      url.hostname = browserHostname;
      return url.toString().replace(/\/+$/, '');
    }
  } catch {
    // Preserve the configured value for the caller's normal URL validation.
  }
  return serviceUrl;
}

// Accept a hostname copied from Vercel settings, but always make the request
// target absolute so it cannot be interpreted as a path on the frontend host.
export const API_BASE = alignLocalServiceHost(
  !apiBase || /^https?:\/\//i.test(apiBase) ? apiBase : `https://${apiBase}`
).replace(/\/+$/, '');

export const SOCKET_URL = alignLocalServiceHost(import.meta.env.VITE_SOCKET_URL?.trim() || (
  import.meta.env.PROD ? (API_BASE || browserOrigin) : 'ws://127.0.0.1:8000'
));

export const REALTIME_ENABLED = (
  import.meta.env.VITE_REALTIME_ENABLED ?? (import.meta.env.PROD ? 'false' : 'true')
).trim().toLowerCase() === 'true';

export const REPORT_CENTER_ENABLED = (
  import.meta.env.VITE_REPORT_CENTER_ENABLED ?? 'true'
).trim().toLowerCase() === 'true';

export const API_TIMEOUT_MS = 30_000;
export const API_UPLOAD_TIMEOUT_MS = 120_000;

