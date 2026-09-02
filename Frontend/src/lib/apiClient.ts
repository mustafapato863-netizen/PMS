import { API_BASE } from '../config';
import { clearAuthenticatedQueryState } from './queryClient';

type ApiErrorPayload = {
  message?: unknown;
  detail?: unknown;
};

type AccessTokenResponse = {
  success: boolean;
  message?: string;
  data?: {
    access_token?: string;
    csrf_token?: string;
  };
};

let accessToken: string | null = null;
let tokenRefresh: Promise<boolean> | null = null;

export function getAccessToken(): string | null {
  if (accessToken) return accessToken;
  // One-time migration for sessions created before the refresh-cookie flow.
  const legacyToken = localStorage.getItem('pms_token');
  if (legacyToken) {
    accessToken = legacyToken;
    localStorage.removeItem('pms_token');
  }
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  localStorage.removeItem('pms_token');
}

function readableIssue(issue: unknown): string | null {
  if (typeof issue === 'string' && issue.trim()) return issue;
  if (!issue || typeof issue !== 'object') return null;

  const record = issue as Record<string, unknown>;
  const message = typeof record.msg === 'string'
    ? record.msg.replace(/^Value error,\s*/i, '')
    : typeof record.message === 'string'
      ? record.message
      : null;
  if (!message) return null;

  const location = Array.isArray(record.loc)
    ? record.loc
      .filter((part) => part !== 'body' && typeof part !== 'number')
      .map((part) => String(part).replaceAll('_', ' '))
      .join(' → ')
    : '';
  return location ? `${location}: ${message}` : message;
}

export function apiErrorMessage(payload: unknown, status: number): string {
  if (!payload || typeof payload !== 'object') return `Request failed (HTTP ${status})`;
  const error = payload as ApiErrorPayload;
  const candidate = error.message ?? error.detail;
  if (typeof candidate === 'string' && candidate.trim()) return candidate;
  if (Array.isArray(candidate)) {
    const messages = candidate.map(readableIssue).filter((value): value is string => Boolean(value));
    if (messages.length) return messages.join(' · ');
  }
  const objectMessage = readableIssue(candidate);
  return objectMessage || `Request failed (HTTP ${status})`;
}

export function clearStoredAuthentication(): void {
  setAccessToken(null);
  localStorage.removeItem('pms_token');
  localStorage.removeItem('pms_csrf_token');
  localStorage.removeItem('pms_session_v1');
  localStorage.removeItem('pms_user_role');
}

function getCsrfToken(): string | null {
  const storedToken = localStorage.getItem('pms_csrf_token');
  if (storedToken) return storedToken;
  const cookieName = 'pms_csrf_token=';
  const cookie = document.cookie.split('; ').find((entry) => entry.startsWith(cookieName));
  return cookie ? decodeURIComponent(cookie.slice(cookieName.length)) : null;
}

async function requestRefreshAccessToken(): Promise<boolean> {
  const csrfToken = getCsrfToken();
  const headers: Record<string, string> = {};
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken;

  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers,
  });
  if (!response.ok) return false;
  const payload = await response.json() as AccessTokenResponse;
  const accessToken = payload.data?.access_token;
  if (!payload.success || !accessToken) return false;
  setAccessToken(accessToken);
  if (payload.data?.csrf_token) localStorage.setItem('pms_csrf_token', payload.data.csrf_token);
  return true;
}

export function refreshAccessToken(): Promise<boolean> {
  if (!tokenRefresh) {
    tokenRefresh = requestRefreshAccessToken().finally(() => {
      tokenRefresh = null;
    });
  }
  return tokenRefresh;
}

let sessionTermination: Promise<void> | null = null;

export function terminateClientSession(): Promise<void> {
  clearStoredAuthentication();
  if (!sessionTermination) {
    sessionTermination = clearAuthenticatedQueryState()
      .finally(() => {
        sessionTermination = null;
      });
  }
  return sessionTermination;
}

import { mockUser, mockTeamConfigs, mockPerformanceRecords, mockBalancedScorecardResponse } from './mockData';

const IS_DEMO = import.meta.env.VITE_DEMO_MODE === 'true';

function handleDemoRequest<T>(endpoint: string): T | null {
  try {
    const url = new URL(endpoint.startsWith('http') ? endpoint : `http://localhost${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`);
    const path = url.pathname;

    if (path === '/api/auth/me' || path === '/api/auth/login') {
      return mockUser as unknown as T;
    }
    if (path === '/api/config/teams') {
      return mockTeamConfigs as unknown as T;
    }
    if (path.startsWith('/api/config/teams/')) {
      const team = path.split('/').pop() || 'Marketing';
      return (mockTeamConfigs[team] || mockTeamConfigs.Marketing) as unknown as T;
    }
    if (path === '/api/performance' || path === '/api/performance/overview') {
      const team = url.searchParams.get('team');
      if (team) {
        return mockPerformanceRecords.filter((r) => r.identity.team.toLowerCase() === team.toLowerCase()) as unknown as T;
      }
      return mockPerformanceRecords as unknown as T;
    }
    if (path === '/api/performance/balanced-scorecard') {
      return mockBalancedScorecardResponse as unknown as T;
    }
    if (path.includes('/team-management')) {
      return { teams: ['Inbound', 'Marketing', 'Outbound'], total: 3, scopes: [] } as unknown as T;
    }
  } catch {
    // ignore parse error
  }
  return null;
}

// Central fetch wrapper — adds JWT automatically
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  if (IS_DEMO) {
    const demoData = handleDemoRequest<T>(endpoint);
    if (demoData !== null) {
      return Promise.resolve(demoData);
    }
  }

  const token = getAccessToken();
  const role = localStorage.getItem('pms_user_role') || 'Viewer';

  // Ensure absolute path if endpoint does not start with "/"
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-User-Role': role,
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (cleanEndpoint.includes('/auth/logout')) {
    const csrfToken = getCsrfToken();
    if (csrfToken && !headers['X-CSRF-Token']) headers['X-CSRF-Token'] = csrfToken;
  }

  const res = await fetch(`${API_BASE}${cleanEndpoint}`, {
    ...options,
    headers,
    credentials: 'include',
  }).catch((err) => {
    // If backend is unreachable, fallback to mock demo data
    const fallback = handleDemoRequest<T>(cleanEndpoint);
    if (fallback !== null) return { ok: true, json: () => Promise.resolve(fallback), status: 200 } as unknown as Response;
    throw err;
  });

  if (res.status === 401) {
    // Login and refresh errors belong to their callers.
    if (cleanEndpoint.includes('/auth/login') || cleanEndpoint.includes('/auth/refresh')) {
      return await res.json();
    }

    // Access tokens are intentionally short-lived. One refresh attempt is
    // shared by concurrent requests so a tab cannot rotate the cookie family
    // several times at once.
    if (await refreshAccessToken()) {
      const retryHeaders: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-User-Role': localStorage.getItem('pms_user_role') || 'Viewer',
        ...(options.headers as Record<string, string>),
      };
      const refreshedToken = getAccessToken();
      if (refreshedToken) retryHeaders['Authorization'] = `Bearer ${refreshedToken}`;
      if (cleanEndpoint.includes('/auth/logout')) {
        const csrfToken = getCsrfToken();
        if (csrfToken && !retryHeaders['X-CSRF-Token']) retryHeaders['X-CSRF-Token'] = csrfToken;
      }
      const retry = await fetch(`${API_BASE}${cleanEndpoint}`, {
        ...options,
        headers: retryHeaders,
        credentials: 'include',
      });
      if (retry.status !== 401) {
        if (!retry.ok) {
          const error = await retry.json().catch(() => ({ message: retry.statusText }));
          throw new Error(apiErrorMessage(error, retry.status));
        }
        return retry.json();
      }
    }

    await terminateClientSession();
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(apiErrorMessage(error, res.status));
  }

  return res.json();
}
