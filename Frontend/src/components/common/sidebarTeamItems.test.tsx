import { render } from '@testing-library/react';
import { expect, it } from 'vitest';

import { getTeamIcon, isHiddenTeam, TEAM_ITEMS } from './sidebarTeamItems';


it('uses a syringe icon for nursing teams', () => {
  const { container } = render(getTeamIcon('Nursing'));

  expect(container.querySelector('svg')).toHaveClass('lucide-syringe');
});

it('hides Inbound UAE from navigation without removing its team identity', () => {
  expect(isHiddenTeam('Inbound UAE')).toBe(true);
  expect(TEAM_ITEMS).not.toEqual(
    expect.arrayContaining([expect.objectContaining({ name: 'Inbound UAE' })]),
  );
});
