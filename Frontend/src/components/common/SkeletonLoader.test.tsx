import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { InlineLoadingBadge, ListLoadingSkeleton, PageLoadingSkeleton, PanelLoadingSkeleton } from './SkeletonLoader';

describe('shared loading skeletons', () => {
  it('provides an accessible, layout-preserving page state', () => {
    render(<PageLoadingSkeleton variant="form" label="Preparing report scope" compact />);
    const status = screen.getByRole('status', { name: 'Preparing report scope' });
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveClass('min-h-[420px]');
  });

  it('supports embedded list and detail loading without blank screens', () => {
    render(<><ListLoadingSkeleton label="Loading teams" /><PanelLoadingSkeleton label="Loading plan details" /></>);
    expect(screen.getByRole('status', { name: 'Loading teams' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Loading plan details' })).toBeInTheDocument();
  });

  it('renders a compact animated loading status for card headers', () => {
    render(<InlineLoadingBadge label="Loading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    expect(screen.getByRole('status').querySelector('.animate-spin')).toBeInTheDocument();
  });
});
