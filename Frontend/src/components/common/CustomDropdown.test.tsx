import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import CustomDropdown from './CustomDropdown';

describe('CustomDropdown', () => {
  it('renders its options when the visual trigger is opened', async () => {
    const user = userEvent.setup();
    const { getByRole } = render(
      <CustomDropdown
        ariaLabel="KPI"
        value=""
        options={[
          { value: '', label: 'All KPIs' },
          { value: 'initial_error_rate', label: 'Initial Error Rate' },
        ]}
        onChange={() => undefined}
      />,
    );

    const trigger = getByRole('button', { name: 'KPI' });
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    await user.click(trigger);

    const menu = document.body.querySelector('[data-dropdown-menu="true"]');
    expect(menu).not.toBeNull();
    expect(menu).toHaveTextContent('Initial Error Rate');
  });

  it('supports keyboard selection from the accessible trigger', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { getByRole } = render(<CustomDropdown ariaLabel="KPI" value="" options={['', 'Initial Error Rate']} onChange={onChange} />);

    getByRole('button', { name: 'KPI' }).focus();
    await user.keyboard('{Enter}{ArrowDown}{Enter}');

    expect(onChange).toHaveBeenCalledWith('Initial Error Rate');
  });
});
