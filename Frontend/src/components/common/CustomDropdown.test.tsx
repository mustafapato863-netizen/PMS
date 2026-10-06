import { fireEvent, render, waitFor } from '@testing-library/react';
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

  it('ignores Escape while closed so it never steals focus from other controls (QA BUG-2)', async () => {
    const user = userEvent.setup();
    const { getByRole } = render(
      <>
        <button type="button">Chart point</button>
        <CustomDropdown ariaLabel="Performance level" value="" options={['', 'Employee']} onChange={() => undefined} />
        <CustomDropdown ariaLabel="Team" value="" options={['', 'Inbound']} onChange={() => undefined} />
      </>,
    );
    const point = getByRole('button', { name: 'Chart point' });
    point.focus();
    await user.keyboard('{Escape}');
    // Give a (wrong) requestAnimationFrame focus restore the chance to run.
    await new Promise((resolve) => window.requestAnimationFrame(() => resolve(null)));
    expect(point).toHaveFocus();
  });

  it('still closes on Escape while open and returns focus to its trigger', async () => {
    const user = userEvent.setup();
    const { getByRole } = render(<CustomDropdown ariaLabel="Team" value="" options={['', 'Inbound']} onChange={() => undefined} />);
    const trigger = getByRole('button', { name: 'Team' });
    await user.click(trigger);
    expect(document.body.querySelector('[data-dropdown-menu="true"]')).not.toBeNull();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(document.body.querySelector('[data-dropdown-menu="true"]')).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('closes on an outside click while open', async () => {
    const user = userEvent.setup();
    const { getByRole } = render(
      <>
        <p>Outside</p>
        <CustomDropdown ariaLabel="Team" value="" options={['', 'Inbound']} onChange={() => undefined} />
      </>,
    );
    await user.click(getByRole('button', { name: 'Team' }));
    expect(document.body.querySelector('[data-dropdown-menu="true"]')).not.toBeNull();
    fireEvent.mouseDown(document.body.querySelector('p') as HTMLElement);
    await waitFor(() => expect(document.body.querySelector('[data-dropdown-menu="true"]')).toBeNull());
  });
});
