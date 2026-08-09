import { normalizeTeamName } from '../../hooks/api/useKpiWeights';

export const shouldShowMarketingNavigation = (
  availableFromData: ReadonlySet<string>,
  scopedTeams: ReadonlySet<string> | null,
) => {
  const marketingKey = normalizeTeamName('Marketing');
  return availableFromData.has(`${marketingKey}:Employee`)
    && (!scopedTeams || scopedTeams.has(marketingKey));
};
