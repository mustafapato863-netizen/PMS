import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CorrectiveActionDataPanel } from './CorrectiveActionDataPanel';

const { fetchWithRole } = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole }),
}));

describe('CorrectiveActionDataPanel', () => {
  it('uploads a JSON backup and reports the imported action count', async () => {
    fetchWithRole.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, data: { created: 2, updated: 1 } }),
    });
    const user = userEvent.setup();
    const { container } = render(<CorrectiveActionDataPanel />);

    const file = new File(['{"format":"pms.corrective-actions","version":1,"records":[]}'], 'actions.json', { type: 'application/json' });
    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    await user.upload(input as HTMLInputElement, file);

    await waitFor(() => expect(fetchWithRole).toHaveBeenCalledWith(
      expect.stringContaining('/api/settings/corrective-actions/import'),
      expect.objectContaining({ method: 'POST' }),
    ));
    expect(await screen.findByText('Imported 3 actions (2 new, 1 updated).')).toBeInTheDocument();
  });
});
