export type KpiBetterDirection = 'higher' | 'lower';

/** Green when the move helps this KPI, red when it hurts. Flat stays neutral. */
export function readKpiTrend(
  label: string,
  betterDirection: KpiBetterDirection,
): { text: string; direction: 'up' | 'down' | 'flat'; favorable: boolean | null } {
  const trimmed = label.trim();
  const direction: 'up' | 'down' | 'flat' =
    trimmed.startsWith('▲') || trimmed.startsWith('↑')
      ? 'up'
      : trimmed.startsWith('▼') || trimmed.startsWith('↓')
        ? 'down'
        : 'flat';
  const text = trimmed.replace(/^[▲▼↑↓●]\s*/, '').trim();
  const favorable =
    direction === 'flat'
      ? null
      : (betterDirection === 'higher' && direction === 'up') ||
        (betterDirection === 'lower' && direction === 'down');
  return { text: text || '—', direction, favorable };
}

export function selectableKpiCardClass(selected: boolean): string {
  return `relative flex w-full flex-col overflow-hidden rounded-xl bg-white text-left transition-shadow duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
    selected
      ? 'px-4 pt-4 pb-3.5 shadow-[0_8px_28px_-8px_rgba(15,23,42,0.16)]'
      : 'px-3.5 py-3.5 shadow-[0_4px_20px_-8px_rgba(15,23,42,0.10)] hover:shadow-[0_8px_28px_-8px_rgba(15,23,42,0.14)]'
  }`;
}
