import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import ResponsiveFilters from './ResponsiveFilters';

describe('ResponsiveFilters', () => {
  beforeEach(() => window.localStorage.removeItem('pms:responsive-filter-position:v1'));

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

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Filters' })).not.toBeInTheDocument());
    expect(document.body.style.overflow).toBe('');
    expect(screen.getByRole('button', { name: /Filters, 2 active filters/i })).toHaveFocus();
  });

  it('closes from Done and returns focus to the floating launcher', async () => {
    const user = userEvent.setup();
    render(<ResponsiveFilters label="Team filters"><p>Team filter controls</p></ResponsiveFilters>);

    const launcher = screen.getByRole('button', { name: /Team filters/ });
    await user.click(launcher);
    expect(screen.getByRole('dialog', { name: 'Team filters' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Done' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Team filters' })).not.toBeInTheDocument());
    expect(launcher).toHaveFocus();
  });

  it('lets the launcher move, keeps it in the viewport, and remembers its new position', async () => {
    const firstRender = render(<ResponsiveFilters label="Team filters"><p>Team filter controls</p></ResponsiveFilters>);
    const launcher = screen.getByRole('button', { name: /Team filters/ });
    const launcherShell = launcher.parentElement as HTMLDivElement;
    const initialLeft = Number.parseFloat(launcherShell.style.left);
    const initialTop = Number.parseFloat(launcherShell.style.top);
    expect(initialTop).toBeLessThan(32);

    fireEvent.pointerDown(launcher, { pointerId: 1, button: 0, clientX: initialLeft + 10, clientY: initialTop + 10 });
    fireEvent.pointerMove(launcher, { pointerId: 1, clientX: initialLeft - 180, clientY: initialTop + 70 });
    fireEvent.pointerUp(launcher, { pointerId: 1, clientX: initialLeft - 180, clientY: initialTop + 70 });

    const movedLeft = Number.parseFloat(launcherShell.style.left);
    const movedTop = Number.parseFloat(launcherShell.style.top);
    expect(movedLeft).toBeLessThan(initialLeft);
    expect(movedTop).toBeGreaterThan(initialTop);
    expect(launcher).toHaveAttribute('aria-expanded', 'false');
    await waitFor(() => expect(window.localStorage.getItem('pms:responsive-filter-position:v1')).toContain(`"x":${movedLeft}`));

    firstRender.unmount();
    render(<ResponsiveFilters label="Action filters"><p>Action filter controls</p></ResponsiveFilters>);
    const restoredShell = screen.getByRole('button', { name: /Action filters/ }).parentElement as HTMLDivElement;
    expect(Number.parseFloat(restoredShell.style.left)).toBe(movedLeft);
    expect(Number.parseFloat(restoredShell.style.top)).toBe(movedTop);
  });

  it('supports keyboard repositioning and a reset to the default spot', () => {
    render(<ResponsiveFilters><p>Filter controls</p></ResponsiveFilters>);
    const launcher = screen.getByRole('button', { name: /Filters/ });
    const shell = launcher.parentElement as HTMLDivElement;
    const initialLeft = Number.parseFloat(shell.style.left);

    fireEvent.keyDown(launcher, { key: 'ArrowLeft', altKey: true });
    expect(Number.parseFloat(shell.style.left)).toBe(initialLeft - 24);
    fireEvent.keyDown(launcher, { key: 'Home', altKey: true });
    expect(Number.parseFloat(shell.style.left)).toBe(initialLeft);
  });
});
