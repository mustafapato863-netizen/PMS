import { useCallback, useMemo } from 'react';
import type { RcmGroupFilter } from '../types';
import { useSearchParams } from 'react-router-dom';

const VALID_GROUPS: RcmGroupFilter[] = ['all', 'offshore_egy', 'uae'];

export function useRcmGroupParam(defaultValue: RcmGroupFilter = 'all') {
  const [searchParams, setSearchParams] = useSearchParams();
  const group = useMemo<RcmGroupFilter>(() => {
    const value = searchParams.get('group') as RcmGroupFilter | null;
    return value && VALID_GROUPS.includes(value) ? value : defaultValue;
  }, [defaultValue, searchParams]);

  const setGroup = useCallback((next: RcmGroupFilter, options?: { clearDomain?: boolean }) => {
    const nextParams = new URLSearchParams(searchParams);
    if (next === 'all') nextParams.delete('group');
    else nextParams.set('group', next);
    if (options?.clearDomain) nextParams.delete('domain');
    setSearchParams(nextParams);
  }, [searchParams, setSearchParams]);

  return { group, setGroup };
}
