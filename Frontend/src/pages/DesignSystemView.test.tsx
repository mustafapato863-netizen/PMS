import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import DesignSystemView from './DesignSystemView';

describe('DesignSystemView', () => {
  it('documents the live SGH Hub contract and supports density selection', async () => {
    const user = userEvent.setup();
    render(<DesignSystemView />);

    expect(screen.getByRole('heading', { name: 'SGH Hub design system' })).toBeInTheDocument();
    expect(screen.getByText(/Production tokens and interaction patterns/i)).toBeInTheDocument();
    expect(screen.getByText('--bsc-blue')).toBeInTheDocument();
    expect(screen.getByText('No performance data')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Score, KPI, neon and trend cards' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Recommended future components' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'KPI drilldown drawer' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Export job center' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Region filter preview' })).toHaveValue('All regions');
    expect(screen.getByRole('combobox', { name: 'Month filter preview' })).toHaveValue('June 2026');
    const monthMenu = screen.getByRole('button', { name: 'All months' });
    expect(monthMenu).toBeInTheDocument();
    await user.click(monthMenu);
    expect(screen.getByRole('listbox', { name: 'Month options' })).toBeInTheDocument();
    await user.click(screen.getByRole('option', { name: 'June' }));
    expect(screen.getByRole('button', { name: 'June' })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByRole('img', { name: 'Monthly performance trend chart' })).toBeInTheDocument();

    const compact = screen.getByRole('button', { name: 'Compact' });
    await user.click(compact);
    expect(compact).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('main')).toHaveAttribute('data-density', 'compact');
  });
});
