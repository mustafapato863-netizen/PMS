import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import DesignSystemView from './DesignSystemView';

describe('DesignSystemView', () => {
  it('renders the reference laboratory and supports representative state changes', async () => {
    const user = userEvent.setup();
    render(<DesignSystemView />);

    expect(screen.getByRole('heading', { name: 'Design System Laboratory' })).toBeInTheDocument();
    expect(screen.getByText(/visible only to Admin users/i)).toBeInTheDocument();

    const compact = screen.getByRole('button', { name: 'Compact' });
    await user.click(compact);
    expect(compact).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('tab', { name: /Reviews/ }));
    expect(document.querySelector('.ds-demo-caption')).toHaveTextContent('Active view: Reviews');

    await user.click(screen.getByRole('button', { name: 'Close dialog' }));
    expect(screen.getByRole('button', { name: 'Open example dialog' })).toBeInTheDocument();
  });
});
