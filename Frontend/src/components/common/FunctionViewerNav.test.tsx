import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import FunctionViewerNav from './FunctionViewerNav';

describe('FunctionViewerNav team links', () => {
  it('links each team of an allowed function to its canonical team page', () => {
    render(<MemoryRouter><FunctionViewerNav
      allowed={['RCM']}
      catalogTeams={['Pre-Approvals IP Offshore', 'Pre-Approvals OP Dubai', 'Coding', 'Inbound']}
      isCollapsed={false}
      renderLink={(item) => <a href={item.path}>{item.name}</a>}
    /></MemoryRouter>);

    const group = screen.getByRole('group', { name: 'RCM teams' });
    expect(within(group).getByRole('link', { name: 'Pre-Approvals IP Offshore' })).toHaveAttribute('href', '/team/pre-approvals');
    expect(within(group).getByRole('link', { name: 'Pre-Approvals OP Final' })).toHaveAttribute('href', '/team/pre-approvals-op-final');
    expect(within(group).getByRole('link', { name: 'Coding' })).toHaveAttribute('href', '/team/coding');
    expect(within(group).queryByRole('link', { name: 'Inbound' })).not.toBeInTheDocument();
  });
});
