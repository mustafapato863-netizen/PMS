import { API_BASE } from '../config';
import { clearAuthenticatedQueryState } from './queryClient';

type ApiErrorPayload = {
  message?: unknown;
  detail?: unknown;
};

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
  localStorage.removeItem('pms_token');
  localStorage.removeItem('pms_session_v1');
  localStorage.removeItem('pms_user_role');
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

// Central fetch wrapper — adds JWT automatically
export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = localStorage.getItem('pms_token');
  const role = localStorage.getItem('pms_user_role') || 'Viewer';

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-User-Role': role,
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Ensure absolute path if endpoint does not start with "/"
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  const res = await fetch(`${API_BASE}${cleanEndpoint}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // For login endpoint, return error response without redirect
    if (cleanEndpoint.includes('/auth/login')) {
      return await res.json();
    }
    // Token expired for other endpoints – clear auth and redirect to login
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
