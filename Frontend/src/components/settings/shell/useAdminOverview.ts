import { useQuery } from '@tanstack/react-query';
import { API_BASE } from '../../../config';
import { useUserRole } from '../../../context/RoleContext';
import { SYSTEM_ERROR_LIMIT, currentTime, parseUploads, readRows, summarizeSystemErrors, summarizeUsers, type OverviewUpload } from './adminOverviewData';

type FetchWithRole = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export const ADMIN_OVERVIEW_QUERY_KEYS = {
  uploads: ['admin-overview', 'uploads'],
  users: ['admin-overview', 'users'],
  systemErrors: ['admin-overview', 'system-errors'],
} as const;

/** A request that fails or returns an unreadable body rejects, so only its own card shows the error. */
async function requestRows(fetchWithRole: FetchWithRole, url: string, signal?: AbortSignal): Promise<unknown[]> {
  const response = await fetchWithRole(url, { signal });
  const body: unknown = await response.json().catch(() => null);
  const rows = readRows(body);
  if (!response.ok || rows === null) throw new Error(`Overview request failed: ${url}`);
  return rows;
}

/**
 * Overview data for the three status cards. Each query is independent: a failure in one never
 * blanks the others. No polling. Refetch happens on mount and when a card's Retry is pressed.
 */
export function useAdminOverview() {
  const { fetchWithRole } = useUserRole();
  const options = { retry: false, refetchOnWindowFocus: false } as const;

  const uploads = useQuery({
    queryKey: ADMIN_OVERVIEW_QUERY_KEYS.uploads,
    queryFn: async ({ signal }): Promise<OverviewUpload[]> => {
      // Same two requests, in the same order, as the upload panel's loadUploads.
      const [employee, management] = await Promise.all([
        requestRows(fetchWithRole, `${API_BASE}/api/uploads/`, signal),
        requestRows(fetchWithRole, `${API_BASE}/api/team-management/management-kpi-config/uploads`, signal),
      ]);
      return [...parseUploads(employee, 'employee'), ...parseUploads(management, 'management')];
    },
    ...options,
  });

  const users = useQuery({
    queryKey: ADMIN_OVERVIEW_QUERY_KEYS.users,
    queryFn: async ({ signal }) => summarizeUsers(await requestRows(fetchWithRole, `${API_BASE}/api/users/`, signal)),
    ...options,
  });

  const systemErrors = useQuery({
    queryKey: ADMIN_OVERVIEW_QUERY_KEYS.systemErrors,
    queryFn: async ({ signal }) => {
      // The endpoint returns the newest rows with no time filter, so fetch its largest page and count the window here.
      const query = new URLSearchParams({ limit: String(SYSTEM_ERROR_LIMIT) });
      const rows = await requestRows(fetchWithRole, `${API_BASE}/api/settings/system-errors?${query}`, signal);
      return summarizeSystemErrors(rows, currentTime());
    },
    ...options,
  });

  return { uploads, users, systemErrors };
}
