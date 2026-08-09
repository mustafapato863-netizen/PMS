import { useSearchParams } from 'react-router-dom';
import type { PerformanceLevelFilter } from '../types';

const LEVELS = new Set<PerformanceLevelFilter>(['All', 'Employee', 'Managerial', 'Corporate']);

export function usePerformanceLevelParam(defaultLevel: PerformanceLevelFilter = 'All') {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawLevel = searchParams.get('performance_level') as PerformanceLevelFilter | null;
  const performanceLevel = rawLevel && LEVELS.has(rawLevel) ? rawLevel : defaultLevel;

  const setPerformanceLevel = (level: PerformanceLevelFilter) => {
    const next = new URLSearchParams(searchParams);
    next.set('performance_level', level);
    setSearchParams(next);
  };

  return { performanceLevel, setPerformanceLevel };
}
