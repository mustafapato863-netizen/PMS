import { useSearchParams } from 'react-router-dom';
import type { LocationKey } from '../types';

const LOCATION_KEYS = new Set<LocationKey>(['all', 'dubai', 'sharjah', 'ajman', 'clinics']);

export function useLocationParam(defaultLocation: LocationKey = 'all') {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedLocation = searchParams.get('branch') || searchParams.get('location');
  const location = requestedLocation && LOCATION_KEYS.has(requestedLocation as LocationKey)
    ? requestedLocation as LocationKey
    : defaultLocation;

  const setLocation = (newLocation: LocationKey) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('branch', newLocation);
    newParams.set('location', newLocation);
    setSearchParams(newParams);
  };

  return { location, setLocation };
}

/**
 * Multi-branch variant used by merged branch teams. The selection is stored as
 * a comma-separated query value so links remain shareable and the legacy
 * single-branch `branch`/`location` parameters continue to work.
 */
export function useLocationsParam(defaultLocations: LocationKey[] = ['all']) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('branches') || searchParams.get('branch') || searchParams.get('location');
  const parsed = (requested || '')
    .split(',')
    .map((value) => value.trim() as LocationKey)
    .filter((value): value is LocationKey => LOCATION_KEYS.has(value));
  const locations = parsed.length > 0 ? parsed : defaultLocations;

  const setLocations = (next: LocationKey[]) => {
    const unique = Array.from(new Set(next));
    const normalized = unique.length === 0 || unique.includes('all') ? ['all' as LocationKey] : unique;
    const encoded = normalized.join(',');
    const newParams = new URLSearchParams(searchParams);
    newParams.set('branches', encoded);
    // Keep the legacy keys in sync for deep links and older consumers.
    newParams.set('branch', encoded);
    newParams.set('location', normalized.length === 1 ? normalized[0] : 'all');
    setSearchParams(newParams);
  };

  return { locations, setLocations };
}
