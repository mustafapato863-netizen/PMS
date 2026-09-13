import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import ResponsiveFilters from './ResponsiveFilters';

describe('ResponsiveFilters', () => {
  it('opens a labeled filter sheet and closes it with Escape', async () => {
    const user = userEvent.setup();

    render(
      <ResponsiveFilters activeCount={2}>
        <label htmlFor="team-filter">Team</label>
        <select id="team-filter" aria-label="Team filter" defaultValue="all">
          <option value="all">All teams</option>
        </select>
      </ResponsiveFilters>,
    );

    await user.click(screen.getByRole('button', { name: /Filters, 2 active filters/i }));

    expect(screen.getByRole('dialog', { name: 'Filters' })).toBeInTheDocument();
    expect(document.body.style.overflow).toBe('hidden');

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: 'Filters' })).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe('');
  });
});
