import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import RouteGuard from './RouteGuard';

const roleState = vi.hoisted(() => ({ role: 'General Manager' as string }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role }),
}));

const PRODUCT = ['Admin', 'General Manager'];
const REPORTS = ['Admin', 'General Manager', 'Manager', 'Executive', 'Viewer'];
const CORRECTIVE = ['Admin', 'Executive', 'General Manager'];

/** Mirrors the guard configuration used in App.tsx for the routes under test. */
const renderAt = (path: string) => render(
  <MemoryRouter initialEntries={[path]}>
    <Routes>
      <Route path="/executive" element={<p>Executive page</p>} />
      <Route path="/reports" element={<RouteGuard allowedRoles={REPORTS}><p>Reports page</p></RouteGuard>} />
      <Route path="/reports/new" element={<RouteGuard allowedRoles={PRODUCT}><p>Report builder</p></RouteGuard>} />
      <Route path="/reports/:reportId/edit" element={<RouteGuard allowedRoles={PRODUCT}><p>Report editor</p></RouteGuard>} />
      <Route path="/insights" element={<RouteGuard allowedRoles={PRODUCT}><p>Insights page</p></RouteGuard>} />
      <Route path="/planning" element={<RouteGuard allowedRoles={PRODUCT}><p>Planning page</p></RouteGuard>} />
      <Route path="/corrective-actions" element={<RouteGuard allowedRoles={CORRECTIVE}><p>Corrective actions page</p></RouteGuard>} />
      <Route path="/team-management" element={<RouteGuard allowedRoles={PRODUCT}><p>Team management page</p></RouteGuard>} />
    </Routes>
  </MemoryRouter>,
);

describe('RouteGuard with the General Manager role string', () => {
  it.each([
    ['/reports', 'Reports page'],
    ['/reports/new', 'Report builder'],
    ['/reports/r1/edit', 'Report editor'],
    ['/insights', 'Insights page'],
    ['/planning', 'Planning page'],
    ['/corrective-actions', 'Corrective actions page'],
    ['/team-management', 'Team management page'],
  ])('lets a General Manager open %s', (path, text) => {
    roleState.role = 'General Manager';
    renderAt(path);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it.each(['/reports/new', '/insights', '/planning', '/corrective-actions', '/team-management'])(
    'redirects a Manager away from %s',
    (path) => {
      roleState.role = 'Manager';
      renderAt(path);
      expect(screen.getByText('Executive page')).toBeInTheDocument();
    },
  );

  it('keeps Reports open for Manager and Corrective Actions open for Executive', () => {
    roleState.role = 'Manager';
    const { unmount } = renderAt('/reports');
    expect(screen.getByText('Reports page')).toBeInTheDocument();
    unmount();

    roleState.role = 'Executive';
    renderAt('/corrective-actions');
    expect(screen.getByText('Corrective actions page')).toBeInTheDocument();
  });
});
