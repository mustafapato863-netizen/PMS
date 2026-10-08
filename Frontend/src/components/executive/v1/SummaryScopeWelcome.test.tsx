import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { User } from '../../../types';
import type { ExecutiveScope } from '../../../features/executive/types';
import SummaryScopeWelcome from './SummaryScopeWelcome';
import { summaryViewLabel } from '../../../features/executive/viewModel';

const user: User = { id: 'u1', username: 'test', name: 'Laila', role: 'Admin' };
const scope: ExecutiveScope = {
  view: 'corporate', role: 'Admin', locked: { region: false, function: false, team: false },
  team: null, function: null, region: null, accessible_functions: [],
};

describe('Summary scope welcome', () => {
  it.each([
    { role: 'Admin', grant: {}, text: /company-wide performance/, label: 'Company view' },
    { role: 'Performance Team', grant: {}, text: /company-wide performance/, label: 'Company view' },
    { role: 'Branch Director', grant: { accessible_branches: ['dubai', 'ajman'] }, text: /assigned branches: Dubai, Ajman/, label: 'Branch view' },
    { role: 'Regional Manager', grant: { accessible_regions: ['UAE', 'EGY'] }, text: /assigned regions: UAE, EGY/, label: 'Regional view' },
    { role: 'Function Director', grant: { accessible_functions: ['RCM', 'Pharmacy'] }, text: /assigned functions \(RCM, Pharmacy\).*across branches/, label: 'Function view' },
    { role: 'Manager', grant: { accessible_teams: ['Inbound'] }, text: /assigned teams \(Inbound\)/, label: 'Team view' },
    { role: 'Employee', grant: {}, text: /your own performance only/, label: 'Authorized scope view' },
    { role: 'Viewer', grant: {}, text: /only the performance data you are authorized/, label: 'Authorized scope view' },
  ])('explains $role scope without changing grants', ({ role, grant, text, label }) => {
    render(<SummaryScopeWelcome role={role} user={{ ...user, ...grant }} scope={scope} />);
    expect(screen.getByText('Welcome, Laila.')).toBeInTheDocument();
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(summaryViewLabel(role, role === 'Manager' ? 'managerial' : 'corporate')).toBe(label);
  });

  it('describes the actual summary scope separately from company-wide access', () => {
    render(<SummaryScopeWelcome role="Admin" user={user} scope={{ ...scope, region: 'UAE', branch: 'dubai', function: 'RCM', team: 'Coding', performance_level: 'Corporate' }} />);
    expect(screen.getByText(/Showing:/)).toHaveTextContent('Region: UAE · Branch: Dubai · Function: RCM · Team: Coding · Level: Corporate');
    expect(screen.getByText(/Showing:/)).not.toHaveTextContent('All performance levels');
  });

  it('includes the Marketing position and defaults to all performance levels', () => {
    render(<SummaryScopeWelcome role="Function Director" user={{ ...user, accessible_functions: ['Marketing'] }} scope={{ ...scope, function: 'Marketing', position: 'Media Buyer' }} />);
    expect(screen.getByText(/Showing:/)).toHaveTextContent('Function: Marketing · Role: Media Buyer · All performance levels');
  });

  it('does not imply company-wide access when no branch is assigned', () => {
    render(<SummaryScopeWelcome role="Branch Director" user={user} />);
    expect(screen.getByText(/confirm your branch assignment/)).toBeInTheDocument();
    expect(screen.queryByText(/company-wide/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing:/)).not.toBeInTheDocument();
  });

  it('stays neutral while the user and summary load', () => {
    render(<SummaryScopeWelcome role="Viewer" user={null} />);
    expect(screen.getByText('Welcome.')).toBeInTheDocument();
    expect(screen.queryByText(/company-wide/)).not.toBeInTheDocument();
  });
});
