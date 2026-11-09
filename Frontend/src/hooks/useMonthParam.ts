import { useSearchParams } from 'react-router-dom';
import { monthNameFromPeriodKey } from './api/scopedPeriod';

const MONTH_ORDER: Record<string, number> = {
  January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
  July: 7, August: 8, September: 9, October: 10, November: 11, December: 12,
};

export function useMonthParam(defaultMonth = 'All') {
  const [searchParams, setSearchParams] = useSearchParams();
  const month = monthNameFromPeriodKey(searchParams.get('period') ?? '') || searchParams.get('month') || defaultMonth;

  const setMonth = (newMonth: string) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('month', newMonth);
    if (newParams.has('period')) newParams.delete('period');
    setSearchParams(newParams);
  };

  return { month, setMonth, MONTH_ORDER };
}
