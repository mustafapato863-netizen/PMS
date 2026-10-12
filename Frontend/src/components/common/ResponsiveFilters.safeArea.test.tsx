import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import ResponsiveFilters from './ResponsiveFilters';

const STORAGE_KEY = 'pms:responsive-filter-position:v1';
const mounted: HTMLElement[] = [];

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: height });
}

/** A header of the given height, mounted the way the app shell mounts it. */
function mountHeader(height: number) {
  const header = document.createElement('header');
  header.className = 'app-header';
  Object.defineProperty(header, 'offsetHeight', { configurable: true, value: height });
  document.body.appendChild(header);
  mounted.push(header);
  return header;
}

/** The bottom dock, shown with its top edge at the given y. */
function mountDock(top: number) {
  const dock = document.createElement('nav');
  dock.className = 'navigation-dock';
  dock.getBoundingClientRect = () => ({ top, bottom: top + 60, left: 0, right: 0, width: 0, height: 60, x: 0, y: top, toJSON: () => ({}) }) as DOMRect;
  document.body.appendChild(dock);
  mounted.push(dock);
  return dock;
}

function renderLauncher() {
  render(<ResponsiveFilters label="Team filters"><p>Team filter controls</p></ResponsiveFilters>);
  const shell = screen.getByRole('button', { name: /Team filters/ }).parentElement as HTMLDivElement;
  return { shell, position: () => ({ x: Number.parseFloat(shell.style.left), y: Number.parseFloat(shell.style.top) }) };
}

describe('ResponsiveFilters safe area', () => {
  beforeEach(() => {
    window.localStorage.removeItem(STORAGE_KEY);
    setViewport(1024, 768);
  });

  afterEach(() => {
    mounted.splice(0).forEach((element) => element.remove());
    setViewport(1024, 768);
  });

  it('starts at the top-right of the area below the header', () => {
    mountHeader(54);
    const { position } = renderLauncher();
    // 1024 wide: 54px button and the 14px edge. Top is the 54px header plus the same edge.
    expect(position()).toEqual({ x: 956, y: 68 });
  });

  it('falls back to the window edge when no header or dock is mounted', () => {
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 956, y: 14 });
  });

  it('keeps a stored position that is already inside the safe area exactly', () => {
    mountHeader(54);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 300, y: 200 }));
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 300, y: 200 });
  });

  it('clamps a stored position inside the header band to the top of the safe area', () => {
    mountHeader(54);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 300, y: 20 }));
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 300, y: 68 });
  });

  it('clamps a stored position past the right edge into the safe area', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 5000, y: 200 }));
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 956, y: 200 });
  });

  it('stops above the bottom dock when the dock is shown', () => {
    mountHeader(54);
    mountDock(700);
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 956, y: 68 });
    // Alt+ArrowDown in 24px steps must stop at 700 - 54 - 14 = 632.
    const launcher = screen.getByRole('button', { name: /Team filters/ });
    for (let step = 0; step < 40; step += 1) fireEvent.keyDown(launcher, { key: 'ArrowDown', altKey: true });
    expect(position().y).toBe(632);
  });

  it('re-clamps a stored position when the window narrows', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ x: 900, y: 200 }));
    const { position } = renderLauncher();
    expect(position()).toEqual({ x: 900, y: 200 });

    // Under 640px the button is 50px and the edge is 12px, so the right limit is 600 - 50 - 12 = 538.
    setViewport(600, 768);
    fireEvent(window, new Event('resize'));
    expect(position()).toEqual({ x: 538, y: 200 });
  });

  it('keeps an untouched launcher at the top-right corner as the window changes', () => {
    mountHeader(54);
    const { position } = renderLauncher();
    setViewport(600, 768);
    fireEvent(window, new Event('resize'));
    expect(position()).toEqual({ x: 538, y: 66 });
  });
});
