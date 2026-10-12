import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AdminOverview } from './AdminOverview';

function renderOverview() {
  return render(
    <MemoryRouter>
      <AdminOverview />
    </MemoryRouter>,
  );
}

describe('AdminOverview', () => {
  it('shows one navigation card for each of the four areas', () => {
    renderOverview();
    const list = screen.getByRole('region', { name: 'Areas' }).querySelector('ul');
    expect(list).not.toBeNull();
    const cards = within(list as HTMLElement).getAllByRole('article');
    expect(cards).toHaveLength(4);
    for (const title of ['Data', 'Evaluation', 'Access', 'System']) {
      expect(screen.getByRole('heading', { level: 3, name: title })).toBeInTheDocument();
    }
  });

  it('links each card to its section with a named action', () => {
    renderOverview();
    const expected: Array<[string, string]> = [
      ['Open data uploads', '/settings/data'],
      ['Open evaluation settings', '/settings/evaluation'],
      ['Manage users', '/settings/users'],
      ['Review system errors', '/settings/system-errors'],
    ];
    for (const [name, href] of expected) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    }
  });

  it('says what each area manages', () => {
    renderOverview();
    expect(screen.getByText(/workbooks, and back up or restore corrective action records/)).toBeInTheDocument();
    expect(screen.getByText(/monthly targets, weights and direction/)).toBeInTheDocument();
    expect(screen.getByText(/user accounts, their roles/)).toBeInTheDocument();
    expect(screen.getByText(/recent server failures/)).toBeInTheDocument();
  });
});
