import { render } from '@testing-library/react';
import { expect, it } from 'vitest';

import { getTeamIcon } from './sidebarTeamItems';


it('uses a syringe icon for nursing teams', () => {
  const { container } = render(getTeamIcon('Nursing'));

  expect(container.querySelector('svg')).toHaveClass('lucide-syringe');
});
