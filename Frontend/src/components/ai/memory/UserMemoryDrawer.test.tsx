import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { apiFetch } from '../../../lib/apiClient';
import { UserMemoryDrawer } from './UserMemoryDrawer';

vi.mock('../../../lib/apiClient', () => ({ apiFetch: vi.fn() }));
const mockedApiFetch = vi.mocked(apiFetch);

describe('UserMemoryDrawer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing when closed', () => {
    mockedApiFetch.mockResolvedValue({ memory: null } as never);
    const { container } = render(<UserMemoryDrawer isOpen={false} onClose={() => undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows stored memory when open', async () => {
    mockedApiFetch.mockResolvedValue({
      memory: {
        preferences: { detail_level: 'brief' },
        query_patterns: { frequent_topics: ['score'] },
        interaction_summary: 'Asks about Inbound often',
        feedback_signals: { positive_count: 3 },
      },
    } as never);
    render(<UserMemoryDrawer isOpen onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText('My Profile & Memory')).toBeInTheDocument());
    expect(screen.getByText('Asks about Inbound often')).toBeInTheDocument();
    expect(screen.getByText(/item\(s\) stored/)).toBeInTheDocument();
  });

  it('shows empty state when no memory', async () => {
    mockedApiFetch.mockResolvedValue({ memory: null } as never);
    render(<UserMemoryDrawer isOpen onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText('No memory yet')).toBeInTheDocument());
  });
});
