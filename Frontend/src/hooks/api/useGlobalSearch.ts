import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '../../lib/apiClient';
import {
  buildLocalSearchResults,
  buildRemoteSearchResults,
  type GlobalSearchResponse,
  type SearchGroupId,
  type SearchResultItem,
} from '../../lib/searchNavigation';
import type { User } from '../../types';

const GROUP_ORDER: SearchGroupId[] = ['navigation', 'employees', 'teams', 'actions'];

function useDebouncedValue<T>(value: T, delay: number) {
  const [debounced, setDebounced] = React.useState(value);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);

  return debounced;
}

export function useGlobalSearch({
  open,
  query,
  role,
  currentUser,
}: {
  open: boolean;
  query: string;
  role: User['role'];
  currentUser: User | null;
}) {
  const debouncedQuery = useDebouncedValue(query.trim(), 250);

  const remoteQuery = useQuery({
    queryKey: ['global-search', debouncedQuery],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (debouncedQuery) {
        params.set('q', debouncedQuery);
      }
      params.set('limit', '8');
      const result = await apiFetch<{ success: boolean; data: GlobalSearchResponse }>(`/api/search/global?${params.toString()}`);
      return result.data;
    },
    enabled: open,
    staleTime: 30_000,
  });

  const remoteItems = useMemo(() => {
    if (!remoteQuery.data) {
      return [];
    }
    return buildRemoteSearchResults(remoteQuery.data);
  }, [remoteQuery.data]);

  const firstTeamPath = remoteItems.find((item) => item.group === 'teams')?.path || null;

  const localItems = useMemo(() => buildLocalSearchResults({
    role,
    currentUser,
    firstTeamPath,
    query: debouncedQuery,
  }), [currentUser, debouncedQuery, firstTeamPath, role]);

  const groupedResults = useMemo(() => {
    const allItems = [...localItems, ...remoteItems];
    return GROUP_ORDER.map((group) => ({
      group,
      items: allItems.filter((item) => item.group === group),
    })).filter((entry) => entry.items.length > 0);
  }, [localItems, remoteItems]);

  const flatResults: SearchResultItem[] = useMemo(
    () => groupedResults.flatMap((entry) => entry.items),
    [groupedResults],
  );

  return {
    debouncedQuery,
    groupedResults,
    flatResults,
    isLoading: remoteQuery.isLoading || remoteQuery.isFetching,
    error: remoteQuery.error instanceof Error ? remoteQuery.error.message : null,
  };
}
