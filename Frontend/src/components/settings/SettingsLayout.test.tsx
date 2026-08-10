import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SettingsLayout } from './SettingsLayout';

describe('SettingsLayout', () => {
  it('uses sidebar navigation and reports section changes', async () => {
    const onChange = vi.fn();
    render(<SettingsLayout activeSection="upload" onSectionChange={onChange}><div>Panel content</div></SettingsLayout>);

    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Data Management/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('button', { name: /Corrective Actions/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /User Management/ }));
    expect(onChange).toHaveBeenCalledWith('users');
  });
});
