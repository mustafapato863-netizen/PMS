import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

export function useRcmEgyptTeamParam() {
  const [searchParams, setSearchParams] = useSearchParams();
  const egyTeam = useMemo(() => searchParams.get('egy_team')?.trim() || '', [searchParams]);

  const setEgyTeam = useCallback((next: string) => {
    const nextParams = new URLSearchParams(searchParams);
    if (!next.trim()) nextParams.delete('egy_team');
    else nextParams.set('egy_team', next.trim());
    setSearchParams(nextParams);
  }, [searchParams, setSearchParams]);

  return { egyTeam, setEgyTeam };
}
