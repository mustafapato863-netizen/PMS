import { render } from '@testing-library/react';
import { expect, it } from 'vitest';

import { getTeamIcon, isHiddenTeam, TEAM_ITEMS } from './sidebarTeamItems';


it('uses a syringe icon for nursing teams', () => {
  const { container } = render(getTeamIcon('Nursing'));

  expect(container.querySelector('svg')).toHaveClass('lucide-syringe');
});

it('links each sidebar team item to its canonical team page', () => {
  expect(TEAM_ITEMS.map((item) => [item.name, item.path])).toEqual([
    ['Call Center', '/team/call-center'],
    ['Sales', '/team/sales'],
    ['CSR', '/team/csr'],
    ['Pharmacy', '/team/pharmacy'],
  ]);
});

it('hides Inbound UAE from navigation without removing its team identity', () => {
  expect(isHiddenTeam('Inbound UAE')).toBe(true);
  expect(TEAM_ITEMS).not.toEqual(
    expect.arrayContaining([expect.objectContaining({ name: 'Inbound UAE' })]),
  );
});
