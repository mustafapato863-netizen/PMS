import { useSearchParams } from 'react-router-dom';
import MarketingDashboardView from './MarketingDashboardView';
import TeamDashboardView from './TeamDashboardView';

const isMarketingManagementLevel = (performanceLevel: string | null) =>
  performanceLevel === 'Managerial' || performanceLevel === 'Corporate';

const MarketingTeamRoute = () => {
  const [searchParams] = useSearchParams();
  const performanceLevel = searchParams.get('performance_level');

  return isMarketingManagementLevel(performanceLevel)
    ? <TeamDashboardView teamIdOverride="marketing" />
    : <MarketingDashboardView />;
};

export default MarketingTeamRoute;
