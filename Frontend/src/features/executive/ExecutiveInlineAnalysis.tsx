import { useCallback, useEffect, useMemo } from 'react';
import { createSearchParams, useSearchParams, type SetURLSearchParams } from 'react-router-dom';
import MonthlyPresentationView from '../monthlyPresentation/MonthlyPresentationView';
import { REVIEW_PREFIX } from './executiveReviewParams';

export default function ExecutiveInlineAnalysis() {
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => window.scrollTo({ top: 0 }), []);
  const monthlyParams = useMemo(() => {
    const params = new URLSearchParams();
    for (const [key, value] of searchParams) {
      if (key.startsWith(REVIEW_PREFIX)) params.set(key.slice(REVIEW_PREFIX.length), value);
    }
    return params;
  }, [searchParams]);

  const update: SetURLSearchParams = useCallback((nextInit, options) => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const key of [...next.keys()]) {
        if (key.startsWith(REVIEW_PREFIX)) next.delete(key);
      }
      const changes = createSearchParams(typeof nextInit === 'function' ? nextInit(monthlyParams) : nextInit);
      if (changes.has('deepDive')) {
        for (const [key, value] of changes) next.set(REVIEW_PREFIX + key, value);
      }
      return next;
    }, options);
  }, [monthlyParams, setSearchParams]);

  return (
    <section aria-label="Executive Summary analysis" className="app-page-shell rf-page executive-v1">
      <MonthlyPresentationView inlineAnalysis={{ searchParams: monthlyParams, setSearchParams: update }} />
    </section>
  );
}
