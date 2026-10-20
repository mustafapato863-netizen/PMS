import './PageEnhancements.css';
import { lazy, Suspense } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { resolveTeamRouteId } from '../types';
import {
  isDepartmentManagementLevel,
  isPositionOverviewTeam,
} from '../features/marketing/positionOverviewTeams';

const MarketingDashboardView = lazy(() => import('./MarketingDashboardView'));
const TeamDashboardView = lazy(() => import('./TeamDashboardView'));

const PositionDepartmentRoute = () => {
  const { teamId } = useParams();
  const [searchParams] = useSearchParams();
  const performanceLevel = searchParams.get('performance_level');
  const canonicalTeamId = resolveTeamRouteId(teamId) ?? teamId;
  const overview = isPositionOverviewTeam(canonicalTeamId) && !isDepartmentManagementLevel(performanceLevel);

  return (
    <Suspense fallback={<div className="app-page-shell rf-page" role="status">Loading team…</div>}>
      {overview
        ? <MarketingDashboardView teamId={canonicalTeamId} />
        : <TeamDashboardView />}
    </Suspense>
  );
};

export default PositionDepartmentRoute;
