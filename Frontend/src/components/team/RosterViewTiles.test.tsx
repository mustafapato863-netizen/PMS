import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import RosterViewTiles, { type RosterView } from './RosterViewTiles';

function Harness() {
  const [view, setView] = useState<RosterView>('all');
  return <RosterViewTiles value={view} onChange={setView} />;
}

describe('RosterViewTiles', () => {
  it('shows both choices with the active view exposed without a dropdown', () => {
    render(<Harness />);
    const tiles = within(screen.getByRole('group', { name: 'Employee roster view' }));
    expect(tiles.getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');
    expect(tiles.getByRole('button', { name: 'Top / Bottom' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('switches both ways by click', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'Top / Bottom' }));
    expect(screen.getByRole('button', { name: 'Top / Bottom' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'false');
    await user.click(screen.getByRole('button', { name: 'All Employees' }));
    expect(screen.getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('supports Tab, Enter and Space without custom keyboard interception', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.tab();
    expect(screen.getByRole('button', { name: 'All Employees' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Top / Bottom' })).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('button', { name: 'Top / Bottom' })).toHaveAttribute('aria-pressed', 'true');
    await user.tab({ shift: true });
    await user.keyboard(' ');
    expect(screen.getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');
  });
});
