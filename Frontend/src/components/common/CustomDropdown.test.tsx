import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import CustomDropdown from './CustomDropdown';

describe('CustomDropdown', () => {
  it('renders its options when the visual trigger is opened', async () => {
    const user = userEvent.setup();
    render(
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

    const trigger = document.querySelector('button[aria-hidden="true"]');
    expect(trigger).not.toBeNull();
    await user.click(trigger as HTMLButtonElement);

    const menu = document.body.querySelector('[data-dropdown-menu="true"]');
    expect(menu).not.toBeNull();
    expect(menu).toHaveTextContent('Initial Error Rate');
  });
});
