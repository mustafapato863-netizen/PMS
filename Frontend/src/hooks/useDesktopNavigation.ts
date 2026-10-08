import { useCallback, useSyncExternalStore } from 'react';

const DESKTOP_QUERY = '(min-width: 1280px)';

// Subscribe to the breakpoint, not every resize pixel.
export function useDesktopNavigation(onBreakpointChange?: () => void) {
  const subscribe = useCallback((onChange: () => void) => {
    const media = window.matchMedia(DESKTOP_QUERY);
    const handleChange = () => {
      onBreakpointChange?.();
      onChange();
    };
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [onBreakpointChange]);
  return useSyncExternalStore(subscribe, () => window.matchMedia(DESKTOP_QUERY).matches, () => true);
}
