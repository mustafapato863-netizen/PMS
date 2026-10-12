import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AdminNotice } from './AdminNotice';
import { AdminPageHeader } from './AdminPageHeader';
import { AdminSection } from './AdminSection';

describe('AdminPageHeader', () => {
  it('renders the title as the page heading with its description, badge and actions', () => {
    render(
      <AdminPageHeader
        title="Administration"
        description="Configure data and users."
        badge={<span>Draft</span>}
        actions={<button type="button">Refresh</button>}
      />,
    );
    expect(screen.getByRole('heading', { level: 1, name: 'Administration' })).toBeInTheDocument();
    expect(screen.getByText('Configure data and users.')).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
  });

  it('renders without optional parts', () => {
    render(<AdminPageHeader title="Administration" />);
    expect(screen.getByRole('heading', { level: 1, name: 'Administration' })).toBeInTheDocument();
  });
});

describe('AdminSection', () => {
  it('is labelled by its title and shows its children', () => {
    render(
      <AdminSection title="Areas" description="Choose an area.">
        <p>Section body</p>
      </AdminSection>,
    );
    const region = screen.getByRole('region', { name: 'Areas' });
    expect(region).toHaveTextContent('Choose an area.');
    expect(region).toHaveTextContent('Section body');
  });
});

describe('AdminNotice', () => {
  it('announces an error as an alert', () => {
    render(<AdminNotice tone="error" title="Save failed">Nothing was saved.</AdminNotice>);
    const notice = screen.getByRole('alert');
    expect(notice).toHaveTextContent('Save failed');
    expect(notice).toHaveTextContent('Nothing was saved.');
  });

  it.each(['info', 'success', 'warning'] as const)('announces a %s notice as a status', (tone) => {
    render(<AdminNotice tone={tone}>Saved.</AdminNotice>);
    expect(screen.getByRole('status')).toHaveTextContent('Saved.');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('defaults to the info tone', () => {
    render(<AdminNotice>Information only.</AdminNotice>);
    expect(screen.getByRole('status')).toHaveClass('border-blue-500/25');
  });
});
