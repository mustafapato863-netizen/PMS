import './PageEnhancements.css';
import { useParams, useSearchParams } from 'react-router-dom';
import { resolveTeamRouteId } from '../types';
import {
  isDepartmentManagementLevel,
  isPositionOverviewTeam,
} from '../features/marketing/positionOverviewTeams';
import MarketingDashboardView from './MarketingDashboardView';
import TeamDashboardView from './TeamDashboardView';

const PositionDepartmentRoute = () => {
  const { teamId } = useParams();
  const [searchParams] = useSearchParams();
  const performanceLevel = searchParams.get('performance_level');
  const canonicalTeamId = resolveTeamRouteId(teamId) ?? teamId;

  if (isPositionOverviewTeam(canonicalTeamId) && !isDepartmentManagementLevel(performanceLevel)) {
    return <MarketingDashboardView teamId={canonicalTeamId} />;
  }

  return <TeamDashboardView />;
};

export default PositionDepartmentRoute;
