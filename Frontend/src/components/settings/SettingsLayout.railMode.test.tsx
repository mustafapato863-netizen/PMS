import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ADMIN_RAIL_MIN_WIDTH_PX, SettingsLayout } from './SettingsLayout';
import type { SettingsPage } from './shell/settingsNavigation';

function renderLayout(activePage: SettingsPage) {
  return render(
    <MemoryRouter initialEntries={[`/settings/${activePage}`]}>
      <SettingsLayout activePage={activePage}>
        <div>Panel content</div>
      </SettingsLayout>
    </MemoryRouter>,
  );
}

function layoutParts() {
  const nav = screen.getByRole('navigation', { name: 'Settings sections' });
  const aside = nav.closest('aside') as HTMLElement;
  const grid = aside.parentElement as HTMLElement;
  const area = grid.parentElement as HTMLElement;
  return { area, grid, aside, nav, list: nav.firstElementChild as HTMLElement };
}

function stubScrollTo() {
  const scrollTo = vi.fn();
  Object.defineProperty(Element.prototype, 'scrollTo', { configurable: true, value: scrollTo });
  return scrollTo;
}

describe('SettingsLayout rail mode', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete (Element.prototype as Partial<Element>).scrollTo;
  });

  it('makes the Administration area the size container for the rail, not the window', () => {
    renderLayout('users');
    const { area, grid } = layoutParts();

    expect(area).toHaveClass('@container/settings');
    expect(grid).toHaveClass('grid', `@min-[${ADMIN_RAIL_MIN_WIDTH_PX}px]/settings:grid-cols-[208px_minmax(0,1fr)]`);
  });

  it('uses one threshold for every container query and no viewport breakpoint', () => {
    const { container } = renderLayout('users');
    const thresholds = [...container.innerHTML.matchAll(/@min-\[([^\]]+)\]/g)].map((match) => match[1]);

    expect(thresholds.length).toBeGreaterThan(0);
    expect(new Set(thresholds)).toEqual(new Set([`${ADMIN_RAIL_MIN_WIDTH_PX}px`]));
    expect(container.innerHTML).not.toMatch(/\bxl:/);
  });

  it('keeps the threshold at 900px', () => {
    expect(ADMIN_RAIL_MIN_WIDTH_PX).toBe(900);
  });

  it('lists the same sections, groups and order as the rail did before', () => {
    renderLayout('upload');
    const { nav } = layoutParts();

    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Overview',
      'Data uploads',
      'Corrective action backup',
      'Evaluation settings',
      'Users',
      'System errors',
    ]);
    for (const heading of ['Data', 'Evaluation', 'Access', 'System']) {
      expect(within(nav).getByText(heading)).toBeInTheDocument();
    }
  });

  it('keeps aria-current on the active item and the navigation name', () => {
    renderLayout('users');
    const nav = screen.getByRole('navigation', { name: 'Settings sections' });

    expect(within(nav).getByRole('link', { name: 'Users' })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
  });

  it('scrolls the active item into view when the list lays out as a row', () => {
    const scrollTo = stubScrollTo();
    renderLayout('users');

    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }));
  });

  it('does not scroll the rail when the list lays out as a column', () => {
    const scrollTo = stubScrollTo();
    const realGetComputedStyle = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element, pseudo) => {
      const style = realGetComputedStyle(element, pseudo);
      const isRailList = element instanceof HTMLUListElement && element.parentElement?.tagName === 'NAV';
      return isRailList ? ({ ...style, flexDirection: 'column' } as CSSStyleDeclaration) : style;
    });

    renderLayout('users');

    expect(scrollTo).not.toHaveBeenCalled();
  });

  it('renders without matchMedia or a scrollTo implementation', () => {
    const originalMatchMedia = window.matchMedia;
    Object.assign(window, { matchMedia: undefined });
    try {
      expect(() => renderLayout('kpis')).not.toThrow();
    } finally {
      Object.assign(window, { matchMedia: originalMatchMedia });
    }
  });
});
