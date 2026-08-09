import { useSearchParams } from 'react-router-dom';
import type { RcmDomainFilter } from '../types';

const DOMAIN_VALUES: RcmDomainFilter[] = ['all', 'pre_approvals', 'submission', 're_submission', 'coding'];

export function useRcmDomainParam(defaultDomain: RcmDomainFilter = 'all') {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get('domain') as RcmDomainFilter | null;
  const domain = raw && DOMAIN_VALUES.includes(raw) ? raw : defaultDomain;

  const setDomain = (next: RcmDomainFilter) => {
    const params = new URLSearchParams(searchParams);
    if (next === 'all') params.delete('domain');
    else params.set('domain', next);
    setSearchParams(params);
  };

  return { domain, setDomain };
}
