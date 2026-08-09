import { useSearchParams } from 'react-router-dom';
import type { CallCenterChannelFilter } from '../types';

const CHANNEL_VALUES: CallCenterChannelFilter[] = ['all', 'inbound', 'outbound'];

export function useCallCenterChannelParam(defaultChannel: CallCenterChannelFilter = 'all') {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('channel') as CallCenterChannelFilter | null;
  const channel = raw && CHANNEL_VALUES.includes(raw) ? raw : defaultChannel;

  const setChannel = (next: CallCenterChannelFilter) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('channel');
    else params.set('channel', next);
    setSearchParams(params);
  };

  return { channel, setChannel };
}
